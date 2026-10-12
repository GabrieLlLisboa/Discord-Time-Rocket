import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.backup import ler, salvar
from cogs.json_store import ler_json, salvar_json
from cogs.mod_utils import eh_super_admin_membro
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────────────────────────────────
#  Cog: Clip do Mês
#  Arquivo: cogs/clips.py
#
#  Concurso mensal de clips no canal de clips.
#
#  CICLO (tudo no fuso de Brasília/Bahia):
#
#   🟢 ABERTO   do começo do ciclo até 00:00 do dia 1 do mês seguinte
#      • só entra VÍDEO (arquivo). Imagem, link e mensagem de texto são
#        apagados na hora (a staff pode conversar).
#      • o bot reage com 🚀 em cada vídeo; a galera vota reagindo também.
#      • a última mensagem do canal é sempre o "Voltar ao topo".
#
#   🔒 FINAL    do dia 1 até o dia 3, às 18:00
#      • canal trancado pra envio (continua visível e dá pra reagir).
#      • ficam só os 3 mais votados do mês (autores diferentes); o resto
#        é apagado (antes disso tudo é salvo em data/clips.json).
#      • as reações dos 3 finalistas são ZERADAS e começa a votação final:
#        1 voto por pessoa (trocar de clip troca o voto).
#      • @everyone avisa o início da final.
#
#   🏆 RESULTADO  dia 3, às 18:00
#      • o clip mais votado fica; os outros são apagados.
#      • vencedor ganha medalha no /perfil + cargo (por sequência).
#      • (opcional) o vídeo vencedor é reenviado no canal Hall da Fama.
#      • canal reabre, @everyone avisa e um novo ciclo começa.
#
#  Comandos (administrador):  /clips setup | status | encerrar-agora |
#                              forcar-vencedor | modo-teste
#  Comando público:           /clips historico
#
#  PERMISSÕES DO BOT no canal de clips: Ver canal, Ler histórico, Enviar
#  mensagens, Gerenciar mensagens, Adicionar reações, Anexar arquivos,
#  Mencionar @everyone, Gerenciar canal/permissões (pra trancar) e, no
#  servidor, Gerenciar cargos (o cargo do bot precisa estar ACIMA dos
#  cargos de clips).
#
#  Dados: data/clips.json (gravação atômica via json_store) — o estado do
#  ciclo fica salvo, então se o bot reiniciar ele continua de onde parou.
#  Perfil: data/perfis.json  ->  perfil["clips"] + perfil["medalhas"].
# ─────────────────────────────────────────────────────────────────────────

CANAL_CLIPS_ID = 1559274806044524695

EMOJI_VOTO = "🚀"
EMOJI_VENCEDOR = "🏆"

MAX_CLIPS_POR_PESSOA = 3      # clips por pessoa em cada ciclo
MAX_LEGENDA = 200             # caracteres de legenda junto do vídeo
MAX_FINALISTAS = 3
MIN_PARTICIPANTES = 2         # autores diferentes pra o ciclo valer prêmio
DIA_RESULTADO = 3             # dia do mês seguinte
HORA_RESULTADO = 18           # hora (Brasília) do resultado
MIN_CLIPADOR = 10             # clips enviados pra medalha "Clipador"
RODAPE_ATRASO = 2.0           # segundos de espera antes de refazer o rodapé
MAX_TENTATIVAS_PASSO = 3

ARQUIVO = "data/clips.json"

EXTENSOES_VIDEO = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Bahia")
except Exception:  # sem tzdata (ex.: Windows) — Brasil não tem horário de verão desde 2019
    TZ = timezone(timedelta(hours=-3), "BRT")

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# Cargos por sequência (só quem está "reinando" tem; troca automaticamente).
CARGOS_DEF = {
    "atual": {"nome": "🎬 Melhor Clip Atual",   "cor": 0xD4A843},
    "bi":    {"nome": "🔥 Bicampeão de Clips",  "cor": 0xE67E22},
    "tri":   {"nome": "💎 Tricampeão de Clips", "cor": 0x3498DB},
    "lenda": {"nome": "👑 Lenda dos Clips",     "cor": 0x9B59B6},
}

# Medalhas permanentes do perfil (também listadas em cogs/medalhas.py).
MEDALHAS_CLIPS = {
    "melhor_clip_mes": "🎬 Melhor Clip (Mês)",
    "finalista_clips": "🏅 Finalista de Clips",
    "clipador":        "🎞️ Clipador",
}

CAMPOS_TRAVA = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
}


# ═════════════════════════════════════════════════════════════════════════
#  Funções puras (sem Discord) — fáceis de testar
# ═════════════════════════════════════════════════════════════════════════

def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def nome_mes(ano: int, mes: int) -> str:
    return f"{MESES[mes - 1].capitalize()}/{ano}"


def label_ciclo(ciclo_id: str) -> str:
    try:
        ano, mes = ciclo_id.split("-")
        return nome_mes(int(ano), int(mes))
    except Exception:
        return ciclo_id


def calcular_prazos_calendario(agora: datetime):
    """Fecha às 00:00 do dia 1 do mês seguinte; resultado no dia 3 às 18:00."""
    local = agora.astimezone(TZ)
    ano, mes = local.year, local.month
    if mes == 12:
        ano, mes = ano + 1, 1
    else:
        mes += 1
    fim_aberto = datetime(ano, mes, 1, 0, 0, tzinfo=TZ)
    fim_final = datetime(ano, mes, DIA_RESULTADO, HORA_RESULTADO, 0, tzinfo=TZ)
    return fim_aberto.astimezone(timezone.utc), fim_final.astimezone(timezone.utc)


def calcular_prazos_teste(agora: datetime, aberto_min: int, final_min: int):
    fim_aberto = agora + timedelta(minutes=aberto_min)
    return fim_aberto, fim_aberto + timedelta(minutes=final_min)


def eh_arquivo_video(nome: str, content_type: Optional[str]) -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("video/"):
        return True
    return (nome or "").lower().endswith(EXTENSOES_VIDEO)


def validar_envio(conteudo: str, anexos: list, tem_sticker: bool = False) -> Optional[str]:
    """Devolve None se a mensagem é um envio válido, ou o motivo da recusa.
    `anexos` = lista de (nome_do_arquivo, content_type)."""
    if not anexos:
        return "Este canal é só para **vídeos** (clips). Mensagens, imagens e links não são permitidos."
    if len(anexos) > 1:
        return "Envie **1 vídeo por mensagem**."
    nome, tipo = anexos[0]
    if not eh_arquivo_video(nome, tipo):
        return "Só aceitamos **vídeos** aqui — imagens e outros arquivos não passam."
    if tem_sticker:
        return "Figurinhas não são permitidas no canal de clips."
    texto = (conteudo or "").strip()
    if len(texto) > MAX_LEGENDA:
        return f"A legenda pode ter no máximo **{MAX_LEGENDA} caracteres**."
    if re.search(r"https?://|discord\.gg/|www\.", texto, re.IGNORECASE):
        return "Links não são permitidos — envie o **arquivo** do vídeo."
    return None


def escolher_finalistas(candidatos: dict, votos: dict, limite: int = MAX_FINALISTAS) -> list:
    """Top `limite` clips por voto, no máximo 1 por autor (o melhor de cada).
    Empate: quem postou primeiro. Ignora candidatos marcados como removidos."""
    ativos = {m: c for m, c in candidatos.items() if not c.get("removido")}
    ordem = sorted(ativos, key=lambda m: (-votos.get(m, 0), ativos[m]["enviado_em"], int(m)))
    escolhidos, autores = [], set()
    for m in ordem:
        autor = ativos[m]["autor_id"]
        if autor in autores:
            continue
        autores.add(autor)
        escolhidos.append(m)
        if len(escolhidos) >= limite:
            break
    return escolhidos


def ordenar_final(finalistas: list, votos_final: dict, candidatos: dict) -> list:
    """Final: mais votos; empate -> mais votos no mês; empate -> postou primeiro."""
    return sorted(
        finalistas,
        key=lambda m: (
            -votos_final.get(m, 0),
            -candidatos[m].get("votos_mes", 0),
            candidatos[m]["enviado_em"],
            int(m),
        ),
    )


def proxima_sequencia(streak: dict, vencedor_id: int) -> int:
    if streak.get("vencedor_id") == vencedor_id:
        return int(streak.get("sequencia", 0)) + 1
    return 1


def chave_cargo(sequencia: int) -> str:
    if sequencia >= 4:
        return "lenda"
    return {1: "atual", 2: "bi", 3: "tri"}.get(sequencia, "atual")


def estado_padrao() -> dict:
    return {
        "config": {
            "canal_id": CANAL_CLIPS_ID,
            "hall_canal_id": None,
            "cargos": {},
            "modo_teste": {"ativo": False, "aberto_min": 10, "final_min": 5},
        },
        "ciclo": None,
        "historico": [],
        "streak": {"vencedor_id": None, "sequencia": 0},
        "contador_ciclos": 0,
    }


def carregar_estado() -> dict:
    bruto = ler_json(ARQUIVO, dict)
    estado = estado_padrao()
    if not isinstance(bruto, dict):
        return estado
    for chave, valor in bruto.items():
        if chave == "config" and isinstance(valor, dict):
            estado["config"].update(valor)
        else:
            estado[chave] = valor
    return estado


# ═════════════════════════════════════════════════════════════════════════
#  Cog
# ═════════════════════════════════════════════════════════════════════════

class Clips(commands.Cog):
    clips = app_commands.Group(name="clips", description="Sistema de Clip do Mês.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.estado = carregar_estado()
        self._lock = asyncio.Lock()
        self._rodape_sujo = False
        self._rodape_tarefa: Optional[asyncio.Task] = None
        self._ticks = 0

    # ── ciclo de vida ───────────────────────────────────────────────────
    async def cog_load(self):
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self.agendar_rodape()

    # ── atalhos de estado ───────────────────────────────────────────────
    @property
    def cfg(self) -> dict:
        return self.estado["config"]

    @property
    def ciclo(self) -> Optional[dict]:
        return self.estado.get("ciclo")

    def _salvar(self):
        salvar_json(ARQUIVO, self.estado)

    def _canal(self) -> Optional[discord.TextChannel]:
        canal = self.bot.get_channel(int(self.cfg["canal_id"]))
        return canal if isinstance(canal, discord.TextChannel) else None

    def _erro(self, ciclo: Optional[dict], texto: str):
        print(f"[CLIPS] ⚠️ {texto}")
        if ciclo is not None:
            erros = ciclo.setdefault("erros", [])
            erros.append(f"{agora_utc():%d/%m %H:%M} — {texto}"[:300])
            del erros[:-10]

    def _eh_staff(self, membro) -> bool:
        if not isinstance(membro, discord.Member):
            return False
        p = membro.guild_permissions
        if p.administrator or p.manage_messages or p.manage_channels:
            return True
        if eh_super_admin_membro(membro):
            return True
        return any(r.id in STAFF_IDS for r in membro.roles)

    # ═════════════════════════════════════════════════════════════════════
    #  Recebimento de clips
    # ═════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if message.channel.id != int(self.cfg["canal_id"]):
            return
        if not self.ciclo:
            return
        async with self._lock:
            ciclo = self.ciclo
            if ciclo:
                await self._processar_mensagem(message, ciclo)

    async def _processar_mensagem(self, message: discord.Message, ciclo: dict):
        staff = self._eh_staff(message.author)
        anexos = [(a.filename, a.content_type) for a in message.attachments]
        motivo = validar_envio(message.content, anexos, bool(message.stickers))
        fechado = ciclo["fase"] != "aberto" or bool(ciclo.get("transicao"))

        if fechado:
            if staff:
                self.agendar_rodape()
                return
            await self._rejeitar(
                message,
                "O canal de clips está **fechado** agora (votação final). "
                "Fica ligado que ele reabre já já! 🚀",
            )
            return

        if motivo:
            if staff:  # staff pode conversar no canal
                self.agendar_rodape()
                return
            await self._rejeitar(message, motivo)
            return

        autor_id = message.author.id
        ativos = [
            c for c in ciclo["candidatos"].values()
            if c["autor_id"] == autor_id and not c.get("removido")
        ]
        if len(ativos) >= MAX_CLIPS_POR_PESSOA:
            await self._rejeitar(
                message,
                f"Você já enviou **{MAX_CLIPS_POR_PESSOA} clips** neste ciclo (limite por pessoa). "
                "Se quiser trocar, apague um dos seus.",
            )
            return

        ciclo["candidatos"][str(message.id)] = {
            "autor_id": autor_id,
            "enviado_em": _iso(message.created_at),
            "url": message.jump_url,
            "arquivo": message.attachments[0].filename,
            "removido": False,
        }
        self._salvar()

        try:
            await message.add_reaction(EMOJI_VOTO)
        except discord.HTTPException as e:
            self._erro(ciclo, f"Não consegui reagir no clip {message.id}: {e}")

        self._registrar_envio(message.author)
        self.agendar_rodape()

    async def _rejeitar(self, message: discord.Message, motivo: str):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await message.channel.send(
                f"{message.author.mention} ⚠️ {motivo}",
                delete_after=8,
                allowed_mentions=discord.AllowedMentions(users=[message.author]),
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        ciclo = self.ciclo
        if not ciclo or payload.channel_id != int(self.cfg["canal_id"]):
            return
        c = ciclo["candidatos"].get(str(payload.message_id))
        if c and not c.get("removido"):
            c["removido"] = True
            self._salvar()
        if payload.message_id == ciclo.get("rodape_id"):
            ciclo["rodape_id"] = None
            self._salvar()
            self.agendar_rodape()

    # ── votos (reações) ─────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        ciclo = self.ciclo
        if not ciclo or payload.channel_id != int(self.cfg["canal_id"]):
            return
        if payload.user_id == self.bot.user.id or str(payload.emoji) != EMOJI_VOTO:
            return
        mid = str(payload.message_id)
        c = ciclo["candidatos"].get(mid)
        if not c or c.get("removido"):
            return
        canal = self._canal()
        if canal is None:
            return
        fase = ciclo["fase"]
        if fase == "final" and mid not in ciclo.get("finalistas", []):
            return
        if fase == "aberto" and ciclo.get("transicao"):
            return

        # voto no próprio clip não vale: remove a reação
        if payload.user_id == c["autor_id"]:
            await self._remover_reacao(canal, payload.message_id, payload.user_id)
            return

        # final: 1 voto por pessoa — votar em outro finalista troca o voto
        if fase == "final":
            for outro in ciclo.get("finalistas", []):
                if outro != mid:
                    await self._remover_reacao(canal, int(outro), payload.user_id)

    async def _remover_reacao(self, canal, msg_id: int, user_id: int):
        try:
            await canal.get_partial_message(msg_id).remove_reaction(EMOJI_VOTO, discord.Object(id=user_id))
        except discord.HTTPException:
            pass

    # ═════════════════════════════════════════════════════════════════════
    #  "Voltar ao topo" — sempre a última mensagem do canal
    # ═════════════════════════════════════════════════════════════════════
    def agendar_rodape(self):
        self._rodape_sujo = True
        if self._rodape_tarefa is None or self._rodape_tarefa.done():
            try:
                self._rodape_tarefa = asyncio.get_running_loop().create_task(self._rodape_worker())
            except RuntimeError:
                pass  # sem loop rodando (ex.: import em teste)

    async def _rodape_worker(self):
        # junta várias mensagens seguidas num único repost do rodapé
        while self._rodape_sujo:
            self._rodape_sujo = False
            await asyncio.sleep(RODAPE_ATRASO)
            if self._rodape_sujo:
                continue
            try:
                await self._postar_rodape()
            except Exception as e:
                print(f"[CLIPS] ⚠️ Erro ao refazer o rodapé: {e}")

    async def _postar_rodape(self):
        ciclo = self.ciclo
        canal = self._canal()
        if not ciclo or canal is None or ciclo.get("transicao"):
            return
        topo = None
        async for m in canal.history(limit=1, oldest_first=True):
            topo = m
        if topo is None or topo.id == ciclo.get("rodape_id"):
            return
        nova = await canal.send(
            f"⬆️ [**Voltar ao topo**]({topo.jump_url})",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        antigo = ciclo.get("rodape_id")
        ciclo["rodape_id"] = nova.id
        self._salvar()
        if antigo and antigo != nova.id:
            await self._api_deletar(canal, antigo)

    async def _checar_rodape(self):
        ciclo = self.ciclo
        canal = self._canal()
        if not ciclo or canal is None or ciclo.get("transicao"):
            return
        async for m in canal.history(limit=1):
            if m.id != ciclo.get("rodape_id"):
                self.agendar_rodape()

    # ═════════════════════════════════════════════════════════════════════
    #  Relógio do ciclo
    # ═════════════════════════════════════════════════════════════════════
    @tasks.loop(seconds=30)
    async def tick(self):
        try:
            await self._avancar_ciclo()
            self._ticks += 1
            if self._ticks % 10 == 0:
                await self._checar_rodape()
        except Exception as e:
            print(f"[CLIPS] ❌ Erro no relógio do ciclo: {e}")

    @tick.before_loop
    async def _antes_tick(self):
        await self.bot.wait_until_ready()

    async def _avancar_ciclo(self):
        async with self._lock:
            ciclo = self.ciclo
            canal = self._canal()
            if not ciclo or canal is None:
                return
            agora = agora_utc()

            if ciclo.get("transicao") == "final":
                await self._executar_final(canal, ciclo)
            elif ciclo.get("transicao") == "resultado":
                await self._executar_resultado(canal, ciclo)
            elif ciclo["fase"] == "aberto" and agora >= _dt(ciclo["fim_aberto"]):
                ciclo["transicao"], ciclo["passos"], ciclo["tentativas"] = "final", {}, {}
                self._salvar()
                await self._executar_final(canal, ciclo)
            elif ciclo["fase"] == "final" and agora >= _dt(ciclo["fim_final"]):
                ciclo["transicao"], ciclo["passos"], ciclo["tentativas"] = "resultado", {}, {}
                self._salvar()
                await self._executar_resultado(canal, ciclo)

    async def _passo(self, ciclo: dict, nome: str, func, critico: bool = False) -> bool:
        """Roda um passo da transição uma única vez (idempotente). Se falhar,
        tenta de novo no próximo tick; depois de 3 falhas segue em frente
        (a não ser que seja crítico). Devolve False se deve parar e retomar."""
        passos = ciclo.setdefault("passos", {})
        if passos.get(nome):
            return True
        tentativas = ciclo.setdefault("tentativas", {})
        try:
            await func()
        except Exception as e:
            tentativas[nome] = tentativas.get(nome, 0) + 1
            self._erro(ciclo, f"passo '{nome}' falhou ({tentativas[nome]}x): {e!r}")
            if not critico and tentativas[nome] >= MAX_TENTATIVAS_PASSO:
                passos[nome] = "erro"
                self._salvar()
                return True
            self._salvar()
            return False
        passos[nome] = True
        self._salvar()
        return True

    # ═════════════════════════════════════════════════════════════════════
    #  Transição ABERTO -> FINAL
    # ═════════════════════════════════════════════════════════════════════
    async def _executar_final(self, canal: discord.TextChannel, ciclo: dict):
        # 1) apuração do mês
        async def apurar():
            votos = {}
            for mid, c in ciclo["candidatos"].items():
                if c.get("removido"):
                    continue
                v = await self._contar_votos(canal, int(mid), c["autor_id"])
                if v is None:
                    c["removido"] = True
                    continue
                votos[mid] = v
                c["votos_mes"] = v
            autores = {c["autor_id"] for c in ciclo["candidatos"].values() if not c.get("removido")}
            if len(autores) < MIN_PARTICIPANTES:
                ciclo["_estender"] = True
                return
            ciclo["_estender"] = False
            finalistas = escolher_finalistas(ciclo["candidatos"], votos)
            ciclo["finalistas"] = finalistas
            ciclo["arquivo_mes"] = [
                {
                    "msg_id": mid,
                    "autor_id": c["autor_id"],
                    "votos": votos.get(mid, 0),
                    "enviado_em": c["enviado_em"],
                    "finalista": mid in finalistas,
                }
                for mid, c in ciclo["candidatos"].items() if not c.get("removido")
            ]

        if not await self._passo(ciclo, "apuracao", apurar, critico=True):
            return

        if ciclo.get("_estender"):
            await self._estender_ciclo(canal, ciclo)
            return

        finalistas = ciclo["finalistas"]

        # 2) tranca o canal
        if not await self._passo(ciclo, "trava", lambda: self._travar_canal(canal, ciclo)):
            return

        # 3) apaga o que não é finalista (+ cabeçalho/rodapé antigos)
        async def limpar():
            for mid in list(ciclo["candidatos"]):
                if mid not in finalistas:
                    await self._api_deletar(canal, mid)
            await self._api_deletar(canal, ciclo.get("cabecalho_id"))
            await self._api_deletar(canal, ciclo.get("rodape_id"))
            ciclo["cabecalho_id"] = None
            ciclo["rodape_id"] = None

        if not await self._passo(ciclo, "limpeza", limpar):
            return

        # 4) zera as reações dos finalistas e o bot reage de novo
        async def zerar():
            for mid in finalistas:
                msg = canal.get_partial_message(int(mid))
                await msg.clear_reactions()
                await msg.add_reaction(EMOJI_VOTO)

        if not await self._passo(ciclo, "reacoes", zerar):
            return

        # 5) anúncio da final com @everyone
        async def anunciar():
            msg = await self._enviar_anuncio_final(canal, ciclo)
            ciclo["final_msg_id"] = msg.id

        if not await self._passo(ciclo, "anuncio", anunciar):
            return

        ciclo["fase"] = "final"
        ciclo["transicao"] = None
        ciclo["passos"], ciclo["tentativas"] = {}, {}
        self._salvar()
        print(f"[CLIPS] 🔒 Ciclo {ciclo['id']}: final iniciada com {len(finalistas)} finalista(s).")
        self.agendar_rodape()

    async def _estender_ciclo(self, canal: discord.TextChannel, ciclo: dict):
        """Menos de MIN_PARTICIPANTES autores: sem prêmio, o ciclo segue (nada é apagado)."""
        agora = agora_utc()
        if self.cfg["modo_teste"]["ativo"]:
            mt = self.cfg["modo_teste"]
            fim_aberto, fim_final = calcular_prazos_teste(agora, mt["aberto_min"], mt["final_min"])
        else:
            fim_aberto, fim_final = calcular_prazos_calendario(_dt(ciclo["fim_aberto"]) + timedelta(days=1))
        ciclo["fim_aberto"], ciclo["fim_final"] = _iso(fim_aberto), _iso(fim_final)
        ciclo["transicao"] = None
        ciclo["passos"], ciclo["tentativas"] = {}, {}
        ciclo.pop("_estender", None)
        self._salvar()
        try:
            await canal.send(
                f"⏳ O mês fechou com menos de **{MIN_PARTICIPANTES} participantes**, então não teve prêmio "
                f"desta vez. Os clips continuam valendo e o ciclo foi **estendido até "
                f"{discord.utils.format_dt(fim_aberto, 'F')}**. Bora mandar mais clips! 🚀",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass
        self.agendar_rodape()

    # ═════════════════════════════════════════════════════════════════════
    #  Transição FINAL -> RESULTADO -> novo ciclo
    # ═════════════════════════════════════════════════════════════════════
    async def _executar_resultado(self, canal: discord.TextChannel, ciclo: dict):
        guild = canal.guild
        finalistas = ciclo.get("finalistas", [])

        # 1) apuração da final e escolha do vencedor
        async def apurar():
            votos_final = {}
            for mid in finalistas:
                c = ciclo["candidatos"].get(mid)
                if not c or c.get("removido"):
                    continue
                v = await self._contar_votos(canal, int(mid), c["autor_id"])
                if v is None:
                    c["removido"] = True
                    continue
                votos_final[mid] = v
            validos = [m for m in finalistas if m in votos_final]
            ordem = ordenar_final(validos, votos_final, ciclo["candidatos"])
            forcado = ciclo.get("vencedor_forcado")
            if forcado in ordem:
                ordem.remove(forcado)
                ordem.insert(0, forcado)
            vencedor = None
            for mid in ordem:  # quem saiu do servidor é pulado
                if guild.get_member(ciclo["candidatos"][mid]["autor_id"]) is not None:
                    vencedor = mid
                    break
            ciclo["resultado"] = {
                "vencedor_msg_id": vencedor,
                "vencedor_id": ciclo["candidatos"][vencedor]["autor_id"] if vencedor else None,
                "votos": votos_final.get(vencedor, 0) if vencedor else 0,
                "mes": label_ciclo(ciclo["id"]),
                "ranking": [
                    {
                        "msg_id": m,
                        "autor_id": ciclo["candidatos"][m]["autor_id"],
                        "votos": votos_final.get(m, 0),
                        "votos_mes": ciclo["candidatos"][m].get("votos_mes", 0),
                    }
                    for m in ordem
                ],
                "sequencia": 0,
            }

        if not await self._passo(ciclo, "apuracao", apurar, critico=True):
            return
        res = ciclo["resultado"]

        # 2) histórico + sequência (uma única gravação)
        async def registrar():
            if not res["vencedor_id"]:
                return
            seq = proxima_sequencia(self.estado["streak"], res["vencedor_id"])
            res["sequencia"] = seq
            self.estado["streak"] = {"vencedor_id": res["vencedor_id"], "sequencia": seq}
            self.estado["historico"].append({
                "numero": ciclo.get("numero"),
                "ciclo": ciclo["id"],
                "mes": res["mes"],
                "vencedor_id": res["vencedor_id"],
                "msg_id": res["vencedor_msg_id"],
                "votos": res["votos"],
                "sequencia": seq,
                "finalistas_autores": sorted({r["autor_id"] for r in res["ranking"]}),
                "ranking": res["ranking"],
                "arquivo_mes": ciclo.get("arquivo_mes", []),
                "encerrado_em": _iso(agora_utc()),
            })
            self._salvar()

        if not await self._passo(ciclo, "historico", registrar, critico=True):
            return

        # 3) medalhas no perfil + cargos
        async def premiar():
            autores = {r["autor_id"] for r in res["ranking"]}
            for uid in autores:
                membro = guild.get_member(uid)
                self._sincronizar_perfil(uid, membro.display_name if membro else str(uid))
            if res["vencedor_id"]:
                await self._aplicar_cargos(guild, res["vencedor_id"], res["sequencia"])

        if not await self._passo(ciclo, "premios", premiar):
            return

        # 4) Hall da Fama (reenvia o vídeo, porque o original será apagado)
        async def hall():
            if res["vencedor_msg_id"]:
                await self._postar_hall(guild, canal, res)

        if not await self._passo(ciclo, "hall", hall):
            return

        # 5) limpeza: só o vencedor fica
        async def limpar():
            vencedor = res["vencedor_msg_id"]
            for mid in finalistas:
                if mid != vencedor:
                    await self._api_deletar(canal, mid)
            if vencedor:
                await self._api_deletar(canal, ciclo.get("campeao_anterior_id"))
            await self._api_deletar(canal, ciclo.get("final_msg_id"))
            await self._api_deletar(canal, ciclo.get("rodape_id"))
            ciclo["rodape_id"] = None
            if vencedor:
                msg = canal.get_partial_message(int(vencedor))
                await msg.clear_reactions()
                await msg.add_reaction(EMOJI_VENCEDOR)

        if not await self._passo(ciclo, "limpeza", limpar):
            return

        # 6) destranca o canal
        if not await self._passo(ciclo, "destrava", lambda: self._destravar_canal(canal, ciclo)):
            return

        # 7) novo ciclo + @everyone avisando que reabriu
        async def reabrir():
            if "_novo" not in ciclo:
                campeao = res["vencedor_msg_id"] or ciclo.get("campeao_anterior_id")
                ciclo["_novo"] = self._novo_ciclo(agora_utc(), campeao_anterior_id=campeao)
                self._salvar()
            msg = await self._enviar_reabertura(canal, ciclo["_novo"], res)
            ciclo["_novo"]["cabecalho_id"] = msg.id

        if not await self._passo(ciclo, "reabertura", reabrir, critico=True):
            return
        novo = ciclo.pop("_novo")
        self.estado["ciclo"] = novo
        self._salvar()
        print(f"[CLIPS] 🏆 Ciclo {ciclo['id']} encerrado. Vencedor: {res['vencedor_id']}. Novo ciclo {novo['id']} aberto.")
        self.agendar_rodape()

    # ═════════════════════════════════════════════════════════════════════
    #  Peças do Discord (separadas pra facilitar teste/manutenção)
    # ═════════════════════════════════════════════════════════════════════
    async def _api_deletar(self, canal, msg_id):
        if not msg_id:
            return
        try:
            await canal.get_partial_message(int(msg_id)).delete()
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            self._erro(self.ciclo, f"Não consegui apagar a mensagem {msg_id}: {e}")

    async def _contar_votos(self, canal, msg_id: int, autor_id: int) -> Optional[int]:
        """Votos únicos (só o emoji oficial), sem bots, sem o autor e sem quem
        saiu do servidor. None = a mensagem não existe mais."""
        try:
            msg = await canal.fetch_message(msg_id)
        except discord.NotFound:
            return None
        guild = canal.guild
        for r in msg.reactions:
            if str(r.emoji) != EMOJI_VOTO:
                continue
            votantes = set()
            async for u in r.users():
                if u.bot or u.id == autor_id:
                    continue
                if guild.get_member(u.id) is None:
                    continue
                votantes.add(u.id)
            return len(votantes)
        return 0

    def _resolver_alvo(self, guild: discord.Guild, item: dict):
        if item["tipo"] == "role":
            return guild.get_role(item["id"])
        return guild.get_member(item["id"])

    async def _travar_canal(self, canal: discord.TextChannel, ciclo: dict):
        """Tranca o ENVIO (continua visível e dá pra reagir). Guarda como
        estava antes pra restaurar certinho na reabertura."""
        guild = canal.guild
        if "lock_backup" not in ciclo:
            alvos = [guild.default_role]
            for alvo, ow in canal.overwrites.items():
                if alvo == guild.default_role or ow.send_messages is not True:
                    continue
                if alvo == guild.me or (isinstance(alvo, discord.Role) and alvo in guild.me.roles):
                    continue
                if isinstance(alvo, discord.Role) and alvo.permissions.administrator:
                    continue
                alvos.append(alvo)
            backup = []
            for alvo in alvos:
                ow = canal.overwrites_for(alvo)
                backup.append({
                    "id": alvo.id,
                    "tipo": "role" if isinstance(alvo, discord.Role) else "member",
                    "campos": {c: getattr(ow, c) for c in CAMPOS_TRAVA},
                })
            ciclo["lock_backup"] = backup
            self._salvar()
        for item in ciclo["lock_backup"]:
            alvo = self._resolver_alvo(guild, item)
            if alvo is None:
                continue
            ow = canal.overwrites_for(alvo)
            for campo, valor in CAMPOS_TRAVA.items():
                setattr(ow, campo, valor)
            await canal.set_permissions(alvo, overwrite=ow, reason="Clips: fase final (envios fechados)")

    async def _destravar_canal(self, canal: discord.TextChannel, ciclo: dict):
        guild = canal.guild
        for item in ciclo.get("lock_backup", []):
            alvo = self._resolver_alvo(guild, item)
            if alvo is None:
                continue
            ow = canal.overwrites_for(alvo)
            for campo, valor in item["campos"].items():
                setattr(ow, campo, valor)
            await canal.set_permissions(
                alvo,
                overwrite=None if ow.is_empty() else ow,
                reason="Clips: canal reaberto",
            )
        ciclo.pop("lock_backup", None)
        self._salvar()

    # ── textos / embeds ─────────────────────────────────────────────────
    def _linhas_regras(self, ciclo: dict) -> str:
        fim_aberto = discord.utils.format_dt(_dt(ciclo["fim_aberto"]), "F")
        fim_final = discord.utils.format_dt(_dt(ciclo["fim_final"]), "F")
        return (
            f"• Envie só **vídeos** (arquivo). Imagem, link e mensagem de texto são apagados.\n"
            f"• **1 vídeo por mensagem**, até **{MAX_CLIPS_POR_PESSOA} clips por pessoa** "
            f"e legenda de até {MAX_LEGENDA} caracteres.\n"
            f"• O bot reage com {EMOJI_VOTO} em cada clip — reaja nos que você curtir. "
            f"Voto no próprio clip não conta.\n"
            f"• Envios até {fim_aberto}. Depois disso os **3 mais votados** (autores diferentes) "
            f"vão pra **final**, que termina em {fim_final}.\n"
            f"• O vencedor ganha a medalha **{MEDALHAS_CLIPS['melhor_clip_mes']}** no `/perfil` e um cargo exclusivo!"
        )

    def _embed_ciclo(self, ciclo: dict, resultado: Optional[dict] = None) -> discord.Embed:
        mes = label_ciclo(ciclo["id"])
        emb = discord.Embed(
            title=f"🎬 Clips de {mes} — envios abertos!",
            color=0xD4A843,
            timestamp=agora_utc(),
        )
        if resultado and resultado.get("vencedor_id"):
            linha = (
                f"🏆 **Melhor Clip de {resultado['mes']}:** <@{resultado['vencedor_id']}> "
                f"com **{resultado['votos']}** {EMOJI_VOTO} — o vídeo está logo acima ⬆️"
            )
            if resultado.get("sequencia", 0) >= 2:
                linha += f"\n🔥 **{resultado['sequencia']} meses seguidos** no topo!"
            medalhas = ["🥇", "🥈", "🥉"]
            podio = [
                f"{medalhas[i]} <@{r['autor_id']}> — {r['votos']} {EMOJI_VOTO}"
                for i, r in enumerate(resultado.get("ranking", [])[:3])
            ]
            if podio:
                linha += "\n\n**Final do mês passado**\n" + "\n".join(podio)
            emb.description = linha
        elif resultado is not None:
            emb.description = f"😕 Não teve vencedor em **{resultado.get('mes', 'último mês')}**."
        emb.add_field(name="📜 Como funciona", value=self._linhas_regras(ciclo), inline=False)
        return emb

    async def _enviar_anuncio_final(self, canal: discord.TextChannel, ciclo: dict) -> discord.Message:
        mes = label_ciclo(ciclo["id"])
        medalhas = ["🥇", "🥈", "🥉"]
        linhas = []
        for i, mid in enumerate(ciclo["finalistas"]):
            c = ciclo["candidatos"][mid]
            linhas.append(
                f"{medalhas[i]} <@{c['autor_id']}> — [ver clip]({c['url']}) • "
                f"**{c.get('votos_mes', 0)}** {EMOJI_VOTO} no mês"
            )
        emb = discord.Embed(
            title=f"🔒 Clips de {mes} encerrados — hora da FINAL!",
            description=(
                "Os envios foram fechados e os clips mais votados do mês disputam o título de "
                f"**{MEDALHAS_CLIPS['melhor_clip_mes']}**:\n\n" + "\n".join(linhas) +
                f"\n\nReaja com {EMOJI_VOTO} no seu favorito. Na final vale **1 voto por pessoa** "
                f"(votar em outro clip troca o seu voto) e voto no próprio clip não conta.\n"
                f"⏰ Resultado: {discord.utils.format_dt(_dt(ciclo['fim_final']), 'F')} "
                f"({discord.utils.format_dt(_dt(ciclo['fim_final']), 'R')})"
            ),
            color=0xE74C3C,
            timestamp=agora_utc(),
        )
        return await canal.send(
            "@everyone",
            embed=emb,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )

    async def _enviar_reabertura(self, canal: discord.TextChannel, novo: dict, resultado: dict) -> discord.Message:
        return await canal.send(
            "@everyone 🎬 **O canal de clips está aberto novamente!** Já podem mandar seus clips! 🚀",
            embed=self._embed_ciclo(novo, resultado),
            allowed_mentions=discord.AllowedMentions(everyone=True, users=True),
        )

    async def _postar_hall(self, guild: discord.Guild, canal: discord.TextChannel, res: dict):
        hall_id = self.cfg.get("hall_canal_id")
        hall = guild.get_channel(int(hall_id)) if hall_id else None
        if hall is None:
            return
        try:
            msg = await canal.fetch_message(int(res["vencedor_msg_id"]))
        except discord.NotFound:
            return
        if not msg.attachments:
            return
        anexo = msg.attachments[0]
        emb = discord.Embed(
            title=f"🏆 Melhor Clip de {res['mes']}",
            description=(
                f"Por <@{res['vencedor_id']}> • **{res['votos']}** {EMOJI_VOTO} na final"
                + (f"\n🔥 **{res['sequencia']} meses seguidos!**" if res["sequencia"] >= 2 else "")
                + (f"\n\n_{msg.content}_" if msg.content else "")
            ),
            color=0xD4A843,
            timestamp=agora_utc(),
        )
        arquivo = None
        limite = getattr(guild, "filesize_limit", 8 * 1024 * 1024)
        if anexo.size <= limite:
            try:
                arquivo = await anexo.to_file()
            except discord.HTTPException:
                arquivo = None
        if arquivo is None:
            emb.add_field(
                name="Vídeo",
                value=f"[Abrir clip]({anexo.url}) _(o arquivo era grande demais pra reenviar; o link pode expirar)_",
                inline=False,
            )
            await hall.send(embed=emb, allowed_mentions=discord.AllowedMentions.none())
        else:
            await hall.send(embed=emb, file=arquivo, allowed_mentions=discord.AllowedMentions.none())

    # ── cargos ──────────────────────────────────────────────────────────
    async def _garantir_cargos(self, guild: discord.Guild) -> dict:
        ids = self.cfg.setdefault("cargos", {})
        roles = {}
        for chave, d in CARGOS_DEF.items():
            role = guild.get_role(ids.get(chave, 0)) or discord.utils.get(guild.roles, name=d["nome"])
            if role is None:
                role = await guild.create_role(
                    name=d["nome"],
                    colour=discord.Colour(d["cor"]),
                    mentionable=False,
                    reason="Clip do Mês: cargo automático",
                )
            ids[chave] = role.id
            roles[chave] = role
        self._salvar()
        return roles

    async def _aplicar_cargos(self, guild: discord.Guild, vencedor_id: int, sequencia: int):
        roles = await self._garantir_cargos(guild)
        alvo_chave = chave_cargo(sequencia)
        for chave, role in roles.items():
            for m in list(role.members):
                if m.id != vencedor_id or chave != alvo_chave:
                    await m.remove_roles(role, reason="Clip do Mês: novo campeão")
        vencedor = guild.get_member(vencedor_id)
        if vencedor and roles[alvo_chave] not in vencedor.roles:
            await vencedor.add_roles(roles[alvo_chave], reason=f"Clip do Mês ({sequencia}x seguidas)")

    # ── perfil / medalhas ───────────────────────────────────────────────
    def _perfil(self, perfis: dict, uid: int, nome: str) -> dict:
        sid = str(uid)
        if sid not in perfis:
            perfis[sid] = {"nome": nome, "amistosos": 0, "vitorias": 0, "derrotas": 0}
        dados = perfis[sid]
        dados.setdefault("amistosos", 0)
        dados.setdefault("vitorias", 0)
        dados.setdefault("derrotas", 0)
        dados.setdefault("medalhas", [])
        dados.setdefault("clips", {})
        return dados

    def _aplicar_medalhas(self, dados: dict):
        clips = dados["clips"]
        ganhas = {
            "melhor_clip_mes": clips.get("vitorias", 0) >= 1,
            "finalista_clips": clips.get("finais", 0) >= 1,
            "clipador": clips.get("enviados", 0) >= MIN_CLIPADOR,
        }
        for mid, ok in ganhas.items():
            if ok and mid not in dados["medalhas"]:
                dados["medalhas"].append(mid)

    def _sincronizar_perfil(self, uid: int, nome: str):
        """Recalcula os números de clips do jogador a partir do histórico
        (idempotente — pode rodar de novo sem duplicar nada)."""
        hist = self.estado["historico"]
        ganhas = [h for h in hist if h["vencedor_id"] == uid]
        perfis = ler("perfis")
        dados = self._perfil(perfis, uid, nome)
        clips = dados["clips"]
        clips["vitorias"] = len(ganhas)
        clips["finais"] = sum(1 for h in hist if uid in h.get("finalistas_autores", []))
        clips["melhor_sequencia"] = max([h["sequencia"] for h in ganhas], default=0)
        streak = self.estado["streak"]
        clips["sequencia_atual"] = streak["sequencia"] if streak.get("vencedor_id") == uid else 0
        clips["ultimo_mes"] = ganhas[-1]["mes"] if ganhas else None
        clips.setdefault("enviados", 0)
        self._aplicar_medalhas(dados)
        salvar("perfis", perfis)

    def _registrar_envio(self, membro):
        try:
            perfis = ler("perfis")
            dados = self._perfil(perfis, membro.id, getattr(membro, "display_name", str(membro)))
            dados["clips"]["enviados"] = dados["clips"].get("enviados", 0) + 1
            self._aplicar_medalhas(dados)
            salvar("perfis", perfis)
        except Exception as e:
            print(f"[CLIPS] ⚠️ Não consegui atualizar o perfil de {membro}: {e}")

    # ── criação de ciclo ────────────────────────────────────────────────
    def _novo_ciclo(self, agora: datetime, campeao_anterior_id=None) -> dict:
        self.estado["contador_ciclos"] = self.estado.get("contador_ciclos", 0) + 1
        local = agora.astimezone(TZ)
        mt = self.cfg["modo_teste"]
        if mt["ativo"]:
            fim_aberto, fim_final = calcular_prazos_teste(agora, mt["aberto_min"], mt["final_min"])
        else:
            fim_aberto, fim_final = calcular_prazos_calendario(agora)
        return {
            "numero": self.estado["contador_ciclos"],
            "id": f"{local.year}-{local.month:02d}",
            "fase": "aberto",
            "transicao": None,
            "passos": {},
            "tentativas": {},
            "inicio": _iso(agora),
            "fim_aberto": _iso(fim_aberto),
            "fim_final": _iso(fim_final),
            "cabecalho_id": None,
            "rodape_id": None,
            "final_msg_id": None,
            "campeao_anterior_id": campeao_anterior_id,
            "candidatos": {},
            "finalistas": [],
            "erros": [],
        }

    # ═════════════════════════════════════════════════════════════════════
    #  Comandos
    # ═════════════════════════════════════════════════════════════════════
    async def _exigir_admin(self, interaction: discord.Interaction) -> bool:
        m = interaction.user
        if isinstance(m, discord.Member) and (m.guild_permissions.administrator or eh_super_admin_membro(m)):
            return True
        await interaction.response.send_message("🚫 Só administradores podem usar esse comando.", ephemeral=True)
        return False

    @clips.command(name="setup", description="Configura o Clip do Mês: cria cargos, Hall da Fama e abre o 1º ciclo.")
    @app_commands.describe(
        importar_existentes="Importar os clips já enviados neste mês no canal (padrão: não)",
        criar_hall="Criar o canal Hall da Fama (padrão: sim)",
        canal="Canal de clips (padrão: o canal configurado no código)",
    )
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        importar_existentes: bool = False,
        criar_hall: bool = True,
        canal: Optional[discord.TextChannel] = None,
    ):
        if not await self._exigir_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if canal is not None:
            self.cfg["canal_id"] = canal.id
        canal_clips = self._canal()
        if canal_clips is None:
            await interaction.followup.send("❌ Não encontrei o canal de clips. Informe o parâmetro `canal`.", ephemeral=True)
            return

        avisos = []
        try:
            await self._garantir_cargos(guild)
        except discord.HTTPException as e:
            avisos.append(f"⚠️ Não consegui criar os cargos ({e}). Dê **Gerenciar Cargos** ao bot.")

        if criar_hall and not self.cfg.get("hall_canal_id"):
            try:
                hall = await guild.create_text_channel(
                    "🏆・hall-da-fama",
                    category=canal_clips.category,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=True),
                        guild.me: discord.PermissionOverwrite(
                            send_messages=True, attach_files=True, embed_links=True
                        ),
                    },
                    topic="Os melhores clips de cada mês. 🚀",
                    reason="Clip do Mês: Hall da Fama",
                )
                self.cfg["hall_canal_id"] = hall.id
            except discord.HTTPException as e:
                avisos.append(f"⚠️ Não consegui criar o Hall da Fama ({e}).")

        async with self._lock:
            if self.ciclo:
                self._salvar()
                await interaction.followup.send(
                    "ℹ️ Já existe um ciclo ativo. Cargos e Hall da Fama foram conferidos.\n" + "\n".join(avisos),
                    ephemeral=True,
                )
                return

            agora = agora_utc()
            ciclo = self._novo_ciclo(agora)
            self.estado["ciclo"] = ciclo
            msg = await canal_clips.send(embed=self._embed_ciclo(ciclo), allowed_mentions=discord.AllowedMentions.none())
            ciclo["cabecalho_id"] = msg.id
            self._salvar()

            importados = 0
            if importar_existentes:
                inicio_mes = agora.astimezone(TZ).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                async for m in canal_clips.history(limit=1000, after=inicio_mes, oldest_first=True):
                    if m.author.bot or m.id == msg.id:
                        continue
                    if validar_envio(m.content, [(a.filename, a.content_type) for a in m.attachments], bool(m.stickers)):
                        continue
                    ativos = sum(1 for c in ciclo["candidatos"].values() if c["autor_id"] == m.author.id)
                    if ativos >= MAX_CLIPS_POR_PESSOA:
                        continue
                    ciclo["candidatos"][str(m.id)] = {
                        "autor_id": m.author.id,
                        "enviado_em": _iso(m.created_at),
                        "url": m.jump_url,
                        "arquivo": m.attachments[0].filename,
                        "removido": False,
                    }
                    try:
                        await m.add_reaction(EMOJI_VOTO)
                    except discord.HTTPException:
                        pass
                    importados += 1
                self._salvar()

        self.agendar_rodape()
        await interaction.followup.send(
            f"✅ **Clip do Mês configurado!** Ciclo `{ciclo['id']}` aberto em {canal_clips.mention}.\n"
            f"• Envios até {discord.utils.format_dt(_dt(ciclo['fim_aberto']), 'F')}\n"
            f"• Resultado em {discord.utils.format_dt(_dt(ciclo['fim_final']), 'F')}\n"
            + (f"• {importados} clip(s) importado(s).\n" if importar_existentes else "")
            + "\n".join(avisos),
            ephemeral=True,
        )

    @clips.command(name="status", description="Mostra em que fase está o ciclo e o ranking parcial.")
    async def status_cmd(self, interaction: discord.Interaction):
        if not await self._exigir_admin(interaction):
            return
        ciclo = self.ciclo
        if not ciclo:
            await interaction.response.send_message("ℹ️ Nenhum ciclo ativo. Use `/clips setup`.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        canal = self._canal()
        fase = {"aberto": "🟢 Aberto (recebendo clips)", "final": "🔒 Final (votação)"}.get(ciclo["fase"], ciclo["fase"])
        if ciclo.get("transicao"):
            fase += f" — ⏳ transição `{ciclo['transicao']}` em andamento"
        alvo_ids = ciclo["finalistas"] if ciclo["fase"] == "final" else [
            m for m, c in ciclo["candidatos"].items() if not c.get("removido")
        ]
        placar = []
        for mid in alvo_ids[:25]:
            c = ciclo["candidatos"].get(mid)
            if not c or canal is None:
                continue
            try:
                v = await self._contar_votos(canal, int(mid), c["autor_id"])
            except discord.HTTPException:
                v = None
            if v is not None:
                placar.append((v, mid, c))
        placar.sort(key=lambda t: (-t[0], t[2]["enviado_em"]))
        linhas = [f"`{v:>3}` {EMOJI_VOTO} — <@{c['autor_id']}> [clip]({c['url']})" for v, _, c in placar[:10]]
        emb = discord.Embed(title=f"🎬 Clip do Mês — {label_ciclo(ciclo['id'])}", color=0xD4A843)
        emb.add_field(name="Fase", value=fase, inline=False)
        emb.add_field(name="Fecha envios", value=discord.utils.format_dt(_dt(ciclo["fim_aberto"]), "F"), inline=True)
        emb.add_field(name="Resultado", value=discord.utils.format_dt(_dt(ciclo["fim_final"]), "F"), inline=True)
        emb.add_field(
            name="Clips válidos",
            value=str(sum(1 for c in ciclo["candidatos"].values() if not c.get("removido"))),
            inline=True,
        )
        emb.add_field(name="Ranking parcial", value="\n".join(linhas) or "_Sem clips ainda._", inline=False)
        if self.cfg["modo_teste"]["ativo"]:
            emb.add_field(name="🧪 Modo teste", value="ATIVO (prazos curtos)", inline=False)
        if ciclo.get("erros"):
            emb.add_field(name="⚠️ Últimos erros", value="\n".join(ciclo["erros"][-5:])[:1000], inline=False)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @clips.command(name="encerrar-agora", description="Avança o ciclo agora (aberto→final, final→resultado).")
    async def encerrar_cmd(self, interaction: discord.Interaction):
        if not await self._exigir_admin(interaction):
            return
        ciclo = self.ciclo
        if not ciclo:
            await interaction.response.send_message("ℹ️ Nenhum ciclo ativo.", ephemeral=True)
            return
        if ciclo.get("transicao"):
            await interaction.response.send_message("⏳ Já tem uma transição em andamento.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        chave = "fim_aberto" if ciclo["fase"] == "aberto" else "fim_final"
        ciclo[chave] = _iso(agora_utc())
        self._salvar()
        await self._avancar_ciclo()
        await interaction.followup.send(
            "✅ Transição executada. Use `/clips status` pra ver como ficou.", ephemeral=True
        )

    @clips.command(name="forcar-vencedor", description="Define o vencedor da final (ID da mensagem) e encerra.")
    @app_commands.describe(mensagem_id="ID da mensagem do vídeo (precisa ser um dos finalistas)")
    async def forcar_cmd(self, interaction: discord.Interaction, mensagem_id: str):
        if not await self._exigir_admin(interaction):
            return
        ciclo = self.ciclo
        if not ciclo or ciclo["fase"] != "final" or ciclo.get("transicao"):
            await interaction.response.send_message("ℹ️ Só dá pra forçar durante a fase **final**.", ephemeral=True)
            return
        mid = mensagem_id.strip()
        if mid not in ciclo.get("finalistas", []):
            await interaction.response.send_message("❌ Esse ID não é de um dos finalistas.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ciclo["vencedor_forcado"] = mid
        ciclo["fim_final"] = _iso(agora_utc())
        self._salvar()
        await self._avancar_ciclo()
        await interaction.followup.send("✅ Vencedor forçado e resultado executado.", ephemeral=True)

    @clips.command(name="modo-teste", description="Liga/desliga prazos curtos (minutos) pra testar o ciclo inteiro.")
    @app_commands.describe(
        ativo="Ligar o modo teste?",
        aberto_min="Minutos da fase aberta",
        final_min="Minutos da fase final",
    )
    async def teste_cmd(
        self,
        interaction: discord.Interaction,
        ativo: bool,
        aberto_min: app_commands.Range[int, 1, 1440] = 5,
        final_min: app_commands.Range[int, 1, 1440] = 3,
    ):
        if not await self._exigir_admin(interaction):
            return
        self.cfg["modo_teste"] = {"ativo": ativo, "aberto_min": aberto_min, "final_min": final_min}
        ciclo = self.ciclo
        agora = agora_utc()
        if ciclo and not ciclo.get("transicao"):
            if ativo:
                if ciclo["fase"] == "aberto":
                    fa, ff = calcular_prazos_teste(agora, aberto_min, final_min)
                    ciclo["fim_aberto"], ciclo["fim_final"] = _iso(fa), _iso(ff)
                else:
                    ciclo["fim_final"] = _iso(agora + timedelta(minutes=final_min))
            else:
                if ciclo["fase"] == "aberto":
                    fa, ff = calcular_prazos_calendario(agora)
                    ciclo["fim_aberto"], ciclo["fim_final"] = _iso(fa), _iso(ff)
                else:
                    local = agora.astimezone(TZ)
                    ff = datetime(local.year, local.month, DIA_RESULTADO, HORA_RESULTADO, tzinfo=TZ)
                    ciclo["fim_final"] = _iso(ff)
        self._salvar()
        txt = (
            f"🧪 Modo teste **ligado**: aberto {aberto_min} min + final {final_min} min (a partir de agora)."
            if ativo else "✅ Modo teste **desligado**: prazos voltaram pro calendário normal."
        )
        await interaction.response.send_message(txt, ephemeral=True)

    @clips.command(name="historico", description="Veja os últimos campeões do Clip do Mês.")
    async def historico_cmd(self, interaction: discord.Interaction):
        hist = self.estado["historico"][-10:][::-1]
        if not hist:
            await interaction.response.send_message("📭 Ainda não teve nenhum Clip do Mês.", ephemeral=True)
            return
        linhas = [
            f"🏆 **{h['mes']}** — <@{h['vencedor_id']}> • {h['votos']} {EMOJI_VOTO}"
            + (f" • 🔥 {h['sequencia']}x seguidas" if h["sequencia"] >= 2 else "")
            for h in hist
        ]
        emb = discord.Embed(title="🎬 Campeões do Clip do Mês", description="\n".join(linhas), color=0xD4A843)
        await interaction.response.send_message(embed=emb, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Clips(bot))
