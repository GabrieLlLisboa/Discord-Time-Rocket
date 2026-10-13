import asyncio
import itertools
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.backup import ler, salvar
from cogs.json_store import ler_json, salvar_json
from cogs.mod_utils import eh_super_admin_membro
from cogs.players import CARGOS_RANK, STAFF_IDS

# ─────────────────────────────────────────────────────────────────────────
#  Cog: Amistoso Interno
#  Arquivo: cogs/interno.py
#
#  Competição interna do clube: 1v1, 2v2 e 3v3 entre os próprios membros,
#  com MMR e tiers próprios (separados dos amistosos contra outros times,
#  que continuam no cogs/friendly.py e cogs/resultados.py).
#
#  COMO FUNCIONA
#   1. A staff roda /interno setup canal:#canal — o bot cria os cargos de
#      tier e posta o painel de fila (botões 1v1 / 2v2 / 3v3).
#   2. Os jogadores clicam no modo pra entrar na fila (dá pra estar em mais
#      de uma fila ao mesmo tempo). Quando uma fila enche, o bot monta os
#      dois times MAIS EQUILIBRADOS pelo MMR e abre o lobby: mensagem com
#      os times, nome/senha da sala e uma thread só da partida.
#   3. Depois do jogo, SÓ A STAFF registra o resultado (botões na mensagem
#      da partida ou /interno resultado). O bot calcula o Elo, atualiza o
#      /perfil e troca o cargo de tier de quem subiu/desceu.
#   4. Errou o resultado? /interno desfazer reabre a partida.
#
#  MMR / TIERS
#   • Cada modo tem seu próprio MMR. Quem estreia começa com um MMR
#     "semente" tirado do cargo de rank do clube (Platina 3 = 1000 ...
#     Super Sonic Legend = 1900); sem cargo de rank começa em 1000.
#   • Elo com média do time. K = 40 nas 10 primeiras partidas do modo, 24 depois.
#   • O tier (cargo no Discord) só aparece depois de 5 partidas num modo e
#     usa o MAIOR MMR do jogador entre os modos.
#
#  Dados: data/interno.json (fila, partidas, config) e, por jogador,
#  data/perfis.json -> perfil["interno"][modo] = {mmr, jogos, vitorias, derrotas}.
#
#  PERMISSÕES DO BOT: Gerenciar Cargos (cargo do bot ACIMA dos cargos de tier),
#  Enviar mensagens, Incorporar links, Criar threads públicas e Enviar
#  mensagens em threads no canal do painel.
# ─────────────────────────────────────────────────────────────────────────

ARQUIVO = "data/interno.json"

MODOS = {"1v1": 1, "2v2": 2, "3v3": 3}      # jogadores por time

MMR_PADRAO = 1000
PARTIDAS_CALIBRAGEM = 5        # partidas no modo pra aparecer o tier
PARTIDAS_K_ALTO = 10
K_ALTO = 40
K_NORMAL = 24

FILA_TIMEOUT_MIN = 60          # tira da fila quem ficou parado
PARTIDA_EXPIRA_H = 24          # partida sem resultado é cancelada (sem mexer no MMR)

EMOJI_TIME = {0: "🔵", 1: "🟠"}

# (MMR mínimo, nome, emoji, cor) — do maior pro menor
TIERS = [
    (1900, "Lenda",      "🌌", 0x9B59B6),
    (1700, "Mestre",     "🔥", 0xE74C3C),
    (1500, "Elite",      "💠", 0x3498DB),
    (1300, "Veterano",   "🛡️", 0x2ECC71),
    (1100, "Competidor", "⚔️", 0xE67E22),
    (0,    "Aspirante",  "🌱", 0x95A5A6),
]

# MMR inicial pelo cargo de rank do clube
SEMENTE_TIER = {"Platina": 1000, "Diamante": 1200, "Champion": 1400, "Grand Champion": 1600}
SEMENTE_SSL = 1900
SEMENTE_DIVISAO = {3: 0, 2: 40, 1: 80}


# ═════════════════════════════════════════════════════════════════════════
#  Funções puras (sem Discord) — fáceis de testar
# ═════════════════════════════════════════════════════════════════════════

def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def tier_para_mmr(mmr: int):
    """(nome, emoji, cor) do tier de um MMR."""
    for minimo, nome, emoji, cor in TIERS:
        if mmr >= minimo:
            return nome, emoji, cor
    return TIERS[-1][1], TIERS[-1][2], TIERS[-1][3]


def semente_por_nome_cargo(nome: str) -> Optional[int]:
    """'Grand Champion 2' -> 1640; 'Super Sonic Legend' -> 1900; outro -> None."""
    if nome == "Super Sonic Legend":
        return SEMENTE_SSL
    partes = nome.rsplit(" ", 1)
    if len(partes) != 2 or partes[0] not in SEMENTE_TIER or not partes[1].isdigit():
        return None
    return SEMENTE_TIER[partes[0]] + SEMENTE_DIVISAO.get(int(partes[1]), 0)


_NOME_RANK_POR_ID = {c["id"]: c["nome"] for c in CARGOS_RANK}


def mmr_semente(membro) -> int:
    melhor = None
    for r in getattr(membro, "roles", []):
        nome = _NOME_RANK_POR_ID.get(r.id)
        if nome is None:
            continue
        s = semente_por_nome_cargo(nome)
        if s is not None and (melhor is None or s > melhor):
            melhor = s
    return melhor if melhor is not None else MMR_PADRAO


def balancear(jogadores: list, por_time: int):
    """jogadores = [(id, mmr)] com 2*por_time itens -> (time1, time2) de ids,
    escolhendo a divisão com a menor diferença de MMR total (sorteia entre
    as empatadas, pra não repetir sempre os mesmos times)."""
    total = sum(m for _, m in jogadores)
    melhor_dif, melhores = None, []
    for combo in itertools.combinations(range(len(jogadores)), por_time):
        if 0 not in combo:  # evita contar a mesma divisão duas vezes (espelhada)
            continue
        a = sum(jogadores[i][1] for i in combo)
        dif = abs(a - (total - a))
        if melhor_dif is None or dif < melhor_dif:
            melhor_dif, melhores = dif, [combo]
        elif dif == melhor_dif:
            melhores.append(combo)
    combo = random.choice(melhores)
    t1 = [jogadores[i][0] for i in combo]
    t2 = [jogadores[i][0] for i in range(len(jogadores)) if i not in combo]
    if random.random() < 0.5:
        t1, t2 = t2, t1
    return t1, t2


def k_fator(jogos: int) -> int:
    return K_ALTO if jogos < PARTIDAS_K_ALTO else K_NORMAL


def calcular_deltas(times: list, mmr: dict, jogos: dict, vencedor: int) -> dict:
    """Elo com média do time. times = [[ids], [ids]]; vencedor = 0 ou 1.
    Devolve {id: delta}. Ganhar sempre dá pelo menos +1 e perder, pelo menos -1;
    o MMR nunca fica abaixo de 0."""
    ra = sum(mmr[u] for u in times[0]) / len(times[0])
    rb = sum(mmr[u] for u in times[1]) / len(times[1])
    esperado = [1 / (1 + 10 ** ((rb - ra) / 400)), 1 / (1 + 10 ** ((ra - rb) / 400))]
    deltas = {}
    for i, time in enumerate(times):
        resultado = 1.0 if i == vencedor else 0.0
        for u in time:
            d = round(k_fator(jogos[u]) * (resultado - esperado[i]))
            if d == 0:
                d = 1 if resultado == 1.0 else -1
            if mmr[u] + d < 0:
                d = -mmr[u]
            deltas[u] = d
    return deltas


def estado_padrao() -> dict:
    return {
        "config": {"canal_id": None, "painel_msg_id": None, "cargos": {}},
        "filas": {m: [] for m in MODOS},
        "partidas": {},
        "contador": 0,
    }


def carregar_estado() -> dict:
    bruto = ler_json(ARQUIVO, dict)
    estado = estado_padrao()
    if not isinstance(bruto, dict):
        return estado
    for chave, valor in bruto.items():
        if chave in ("config", "filas") and isinstance(valor, dict):
            estado[chave].update(valor)
        else:
            estado[chave] = valor
    for m in MODOS:
        estado["filas"].setdefault(m, [])
    return estado


def todos_jogadores(partida: dict) -> list:
    return [u for time in partida["times"] for u in time]


# ═════════════════════════════════════════════════════════════════════════
#  Views persistentes (botões continuam funcionando depois de reiniciar)
# ═════════════════════════════════════════════════════════════════════════

class PainelView(discord.ui.View):
    def __init__(self, cog: "Interno"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="1v1", emoji="⚔️", style=discord.ButtonStyle.primary, custom_id="interno:fila:1v1", row=0)
    async def entrar_1v1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.entrar_fila(interaction, "1v1")

    @discord.ui.button(label="2v2", emoji="🤝", style=discord.ButtonStyle.primary, custom_id="interno:fila:2v2", row=0)
    async def entrar_2v2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.entrar_fila(interaction, "2v2")

    @discord.ui.button(label="3v3", emoji="🚀", style=discord.ButtonStyle.primary, custom_id="interno:fila:3v3", row=0)
    async def entrar_3v3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.entrar_fila(interaction, "3v3")

    @discord.ui.button(label="Sair das filas", emoji="🚪", style=discord.ButtonStyle.secondary, custom_id="interno:sair", row=1)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.sair_das_filas(interaction)

    @discord.ui.button(label="Meu rank", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="interno:rank", row=1)
    async def meu_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=self.cog.embed_rank(interaction.user), ephemeral=True)


class ResultadoView(discord.ui.View):
    """Botões da mensagem da partida. A partida é descoberta pelo ID da
    mensagem clicada (igual ao padrão do cogs/whitelist.py)."""

    def __init__(self, cog: "Interno"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Time 1 venceu", emoji="🔵", style=discord.ButtonStyle.success, custom_id="interno:res:1", row=0)
    async def t1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clique_resultado(interaction, 0)

    @discord.ui.button(label="Time 2 venceu", emoji="🟠", style=discord.ButtonStyle.success, custom_id="interno:res:2", row=0)
    async def t2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clique_resultado(interaction, 1)

    @discord.ui.button(label="Cancelar partida", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="interno:res:cancel", row=1)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clique_resultado(interaction, None)


# ═════════════════════════════════════════════════════════════════════════
#  Cog
# ═════════════════════════════════════════════════════════════════════════

class Interno(commands.Cog):
    interno = app_commands.Group(name="interno", description="Amistoso interno do clube (1v1, 2v2, 3v3).")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.estado = carregar_estado()
        self._lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(PainelView(self))
        self.bot.add_view(ResultadoView(self))
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    # ── atalhos ─────────────────────────────────────────────────────────
    @property
    def cfg(self) -> dict:
        return self.estado["config"]

    def _salvar(self):
        salvar_json(ARQUIVO, self.estado)

    def _eh_staff(self, membro) -> bool:
        if not isinstance(membro, discord.Member):
            return False
        if membro.guild_permissions.administrator or eh_super_admin_membro(membro):
            return True
        return any(r.id in STAFF_IDS for r in membro.roles)

    def _partida_aberta_de(self, uid: int) -> Optional[dict]:
        for p in self.estado["partidas"].values():
            if p["status"] == "aberta" and uid in todos_jogadores(p):
                return p
        return None

    def _canal(self) -> Optional[discord.TextChannel]:
        cid = self.cfg.get("canal_id")
        c = self.bot.get_channel(int(cid)) if cid else None
        return c if isinstance(c, discord.TextChannel) else None

    # ── perfil (MMR por modo) ───────────────────────────────────────────
    @staticmethod
    def _perfil(perfis: dict, uid: int, nome: str) -> dict:
        sid = str(uid)
        if sid not in perfis:
            perfis[sid] = {"nome": nome, "amistosos": 0, "vitorias": 0, "derrotas": 0}
        dados = perfis[sid]
        dados.setdefault("amistosos", 0)
        dados.setdefault("vitorias", 0)
        dados.setdefault("derrotas", 0)
        dados.setdefault("interno", {})
        return dados

    def _dados_modo(self, perfis: dict, uid: int, modo: str, membro=None) -> dict:
        nome = getattr(membro, "display_name", str(uid))
        dados = self._perfil(perfis, uid, nome)
        if modo not in dados["interno"]:
            dados["interno"][modo] = {
                "mmr": mmr_semente(membro) if membro is not None else MMR_PADRAO,
                "jogos": 0, "vitorias": 0, "derrotas": 0,
            }
        return dados["interno"][modo]

    @staticmethod
    def tier_geral(perfis: dict, uid: int):
        """Tier (nome, emoji, cor) pelo maior MMR entre os modos já calibrados, ou None."""
        interno = perfis.get(str(uid), {}).get("interno", {})
        calibrados = [d["mmr"] for d in interno.values() if isinstance(d, dict) and d.get("jogos", 0) >= PARTIDAS_CALIBRAGEM]
        return tier_para_mmr(max(calibrados)) if calibrados else None

    # ═════════════════════════════════════════════════════════════════════
    #  Painel e fila
    # ═════════════════════════════════════════════════════════════════════
    def _embed_painel(self) -> discord.Embed:
        emb = discord.Embed(
            title="⚔️ Amistoso Interno — Fila",
            description=(
                "Clique no modo pra entrar na fila. Quando completar, o bot monta os **times equilibrados "
                "pelo MMR** e abre o lobby com uma thread só da partida.\n"
                "O resultado é registrado pela **staff** e atualiza seu MMR, seu tier e o `/perfil`."
            ),
            color=0xD4A843,
            timestamp=agora_utc(),
        )
        for modo, por_time in MODOS.items():
            fila = self.estado["filas"][modo]
            lista = "\n".join(f"▸ <@{e['id']}>" for e in fila) or "_ninguém na fila_"
            emb.add_field(name=f"{modo} — {len(fila)}/{por_time * 2}", value=lista, inline=True)
        abertas = sum(1 for p in self.estado["partidas"].values() if p["status"] == "aberta")
        emb.set_footer(text=f"Partidas em andamento: {abertas} • Fila expira após {FILA_TIMEOUT_MIN} min parado")
        return emb

    async def _atualizar_painel(self, guild: Optional[discord.Guild] = None):
        canal = self._canal()
        mid = self.cfg.get("painel_msg_id")
        if canal is None or not mid:
            return
        try:
            await canal.get_partial_message(int(mid)).edit(embed=self._embed_painel())
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui atualizar o painel: {e}")

    async def entrar_fila(self, interaction: discord.Interaction, modo: str):
        await interaction.response.defer(ephemeral=True)
        guild, membro = interaction.guild, interaction.user
        if guild is None:
            return
        formada = None
        async with self._lock:
            aberta = self._partida_aberta_de(membro.id)
            if aberta:
                await interaction.followup.send(
                    f"⏳ Você está na **partida #{aberta['id']}** ({aberta['modo']}). "
                    "Aguarde a staff registrar o resultado antes de entrar em outra fila.",
                    ephemeral=True,
                )
                return
            fila = self.estado["filas"][modo]
            if any(e["id"] == membro.id for e in fila):
                await interaction.followup.send(
                    f"ℹ️ Você já está na fila de **{modo}** ({len(fila)}/{MODOS[modo] * 2}).", ephemeral=True
                )
                return

            perfis = ler("perfis")
            self._dados_modo(perfis, membro.id, modo, membro)  # garante MMR semente
            salvar("perfis", perfis)

            fila.append({"id": membro.id, "t": _iso(agora_utc())})
            try:
                formada = await self._tentar_formar(guild, modo)
            except (discord.HTTPException, RuntimeError) as e:
                fila[:] = [x for x in fila if x["id"] != membro.id]
                self._salvar()
                await interaction.followup.send(
                    f"❌ Não consegui abrir a partida ({e}). Avise a staff — confira o canal do painel e as permissões do bot.",
                    ephemeral=True,
                )
                return
            self._salvar()

        await self._atualizar_painel(guild)
        if formada:
            canal = self._canal()
            await interaction.followup.send(
                f"🎮 **Partida #{formada['id']} encontrada!** Veja em {canal.mention if canal else 'o canal do painel'}.",
                ephemeral=True,
            )
        else:
            fila = self.estado["filas"][modo]
            await interaction.followup.send(
                f"✅ Você entrou na fila de **{modo}** ({len(fila)}/{MODOS[modo] * 2}). Te marco quando a partida abrir!",
                ephemeral=True,
            )

    async def sair_das_filas(self, interaction: discord.Interaction):
        async with self._lock:
            saiu = False
            for modo in MODOS:
                fila = self.estado["filas"][modo]
                novo = [e for e in fila if e["id"] != interaction.user.id]
                if len(novo) != len(fila):
                    self.estado["filas"][modo] = novo
                    saiu = True
            if saiu:
                self._salvar()
        if saiu:
            await interaction.response.send_message("🚪 Você saiu de todas as filas.", ephemeral=True)
            await self._atualizar_painel(interaction.guild)
        else:
            await interaction.response.send_message("ℹ️ Você não estava em nenhuma fila.", ephemeral=True)

    async def _tentar_formar(self, guild: discord.Guild, modo: str) -> Optional[dict]:
        """Se a fila do modo encheu, monta os times e publica a partida.
        Só altera o estado depois que a mensagem foi enviada com sucesso."""
        fila = self.estado["filas"][modo]
        fila[:] = [e for e in fila if guild.get_member(e["id"]) is not None]
        tamanho = MODOS[modo] * 2
        if len(fila) < tamanho:
            return None

        escolhidos = [e["id"] for e in fila[:tamanho]]
        perfis = ler("perfis")
        mmr = {u: self._dados_modo(perfis, u, modo, guild.get_member(u))["mmr"] for u in escolhidos}
        t1, t2 = balancear([(u, mmr[u]) for u in escolhidos], MODOS[modo])

        pid = int(self.estado["contador"]) + 1
        partida = {
            "id": pid,
            "modo": modo,
            "times": [t1, t2],
            "mmr_antes": {str(u): mmr[u] for u in escolhidos},
            "status": "aberta",
            "criada_em": _iso(agora_utc()),
            "sala": {"nome": f"TH{pid:04d}", "senha": f"{secrets.randbelow(10000):04d}"},
            "msg_id": None,
            "thread_id": None,
        }
        msg, thread = await self._publicar_partida(guild, partida)

        # sucesso: agora sim muda o estado
        partida["msg_id"] = msg.id
        partida["thread_id"] = thread.id if thread else None
        self.estado["contador"] = pid
        self.estado["partidas"][str(pid)] = partida
        for m in MODOS:
            self.estado["filas"][m] = [e for e in self.estado["filas"][m] if e["id"] not in escolhidos]
        print(f"[INTERNO] 🎮 Partida #{pid} ({modo}) criada: {t1} x {t2}")
        return partida

    def _linhas_time(self, partida: dict, idx: int, deltas: Optional[dict] = None) -> str:
        linhas = []
        for u in partida["times"][idx]:
            antes = partida["mmr_antes"][str(u)]
            if deltas is None:
                linhas.append(f"▸ <@{u}> — `{antes}`")
            else:
                d = deltas[str(u)]
                linhas.append(f"▸ <@{u}> — `{antes}` → `{antes + d}` ({'+' if d > 0 else ''}{d})")
        return "\n".join(linhas)

    def _embed_partida(self, partida: dict) -> discord.Embed:
        modo, status = partida["modo"], partida["status"]
        medias = [
            round(sum(partida["mmr_antes"][str(u)] for u in t) / len(t)) for t in partida["times"]
        ]
        if status == "finalizada":
            v = partida["vencedor"]
            emb = discord.Embed(
                title=f"✅ Partida #{partida['id']} — {modo} • {EMOJI_TIME[v]} Time {v + 1} venceu",
                color=0x2ECC71,
            )
            deltas = partida["deltas"]
        elif status == "cancelada":
            emb = discord.Embed(title=f"🚫 Partida #{partida['id']} — {modo} • cancelada", color=0x95A5A6)
            deltas = None
        else:
            emb = discord.Embed(title=f"🎮 Partida #{partida['id']} — {modo}", color=0xD4A843, timestamp=agora_utc())
            deltas = None
        for i in (0, 1):
            vencedor_tag = " 🏆" if status == "finalizada" and partida["vencedor"] == i else ""
            emb.add_field(
                name=f"{EMOJI_TIME[i]} Time {i + 1}{vencedor_tag} • média {medias[i]}",
                value=self._linhas_time(partida, i, deltas),
                inline=True,
            )
        if status == "aberta":
            sala = partida["sala"]
            emb.add_field(
                name="🏟️ Sala (partida privada)",
                value=f"Nome: `{sala['nome']}` • Senha: ||`{sala['senha']}`||\nO **Time 1** cria a sala e o **Time 2** entra.",
                inline=False,
            )
            emb.set_footer(text="Depois do jogo, a staff registra o resultado nos botões abaixo.")
        elif status == "finalizada":
            for t in partida.get("promocoes", []):
                emb.add_field(name="​", value=t, inline=False)
        return emb

    async def _publicar_partida(self, guild: discord.Guild, partida: dict):
        canal = self._canal()
        if canal is None:
            raise RuntimeError("canal do painel não configurado")
        mencoes = " ".join(f"<@{u}>" for u in todos_jogadores(partida))
        msg = await canal.send(
            f"🎮 **Partida encontrada!** {mencoes}",
            embed=self._embed_partida(partida),
            view=ResultadoView(self),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        thread = None
        try:
            thread = await msg.create_thread(name=f"Partida #{partida['id']} • {partida['modo']}", auto_archive_duration=1440)
            await thread.send(
                f"{mencoes}\nBoa partida! Combinem aqui e criem a sala (`{partida['sala']['nome']}`). "
                "Quando acabar, **avisem a staff** pra registrar o resultado. 🚀",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui criar a thread da partida #{partida['id']}: {e}")
        return msg, thread

    # ═════════════════════════════════════════════════════════════════════
    #  Resultado (somente staff)
    # ═════════════════════════════════════════════════════════════════════
    async def clique_resultado(self, interaction: discord.Interaction, vencedor: Optional[int]):
        if not self._eh_staff(interaction.user):
            await interaction.response.send_message("🚫 Só a staff registra o resultado.", ephemeral=True)
            return
        partida = next(
            (p for p in self.estado["partidas"].values() if p.get("msg_id") == interaction.message.id), None
        )
        if partida is None or partida["status"] != "aberta":
            await interaction.response.send_message("ℹ️ Essa partida não está mais aberta.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if vencedor is None:
            ok = await self.cancelar_partida(interaction.guild, partida, interaction.user)
            texto = f"🚫 Partida #{partida['id']} cancelada." if ok else "ℹ️ Essa partida não está mais aberta."
        else:
            res = await self.finalizar_partida(interaction.guild, partida, vencedor, interaction.user)
            texto = (
                f"✅ Partida #{partida['id']} registrada: **Time {vencedor + 1}** venceu."
                if res else "ℹ️ Essa partida não está mais aberta."
            )
        await interaction.followup.send(texto, ephemeral=True)

    async def finalizar_partida(self, guild: discord.Guild, partida: dict, vencedor: int, staff) -> bool:
        async with self._lock:
            if partida["status"] != "aberta":
                return False
            modo = partida["modo"]
            perfis = ler("perfis")
            ids = todos_jogadores(partida)
            mmr, jogos = {}, {}
            for u in ids:
                d = self._dados_modo(perfis, u, modo, guild.get_member(u))
                mmr[u], jogos[u] = d["mmr"], d["jogos"]
            tier_antes = {u: self.tier_geral(perfis, u) for u in ids}
            partida["mmr_antes"] = {str(u): mmr[u] for u in ids}
            deltas = calcular_deltas(partida["times"], mmr, jogos, vencedor)
            for u in ids:
                d = perfis[str(u)]["interno"][modo]
                d["mmr"] += deltas[u]
                d["jogos"] += 1
                d["vitorias" if u in partida["times"][vencedor] else "derrotas"] += 1
            salvar("perfis", perfis)

            promocoes = []
            ordem_tiers = [t[1] for t in TIERS]  # índice menor = tier mais alto
            for u in ids:
                antes, depois = tier_antes[u], self.tier_geral(perfis, u)
                if depois and (antes is None or depois[0] != antes[0]):
                    sobe = antes is None or ordem_tiers.index(depois[0]) < ordem_tiers.index(antes[0])
                    seta = "⬆️" if sobe else "⬇️"
                    promocoes.append(f"{seta} <@{u}> agora é {depois[1]} **{depois[0]}**")

            partida.update({
                "status": "finalizada",
                "vencedor": vencedor,
                "deltas": {str(u): deltas[u] for u in ids},
                "promocoes": promocoes,
                "finalizada_em": _iso(agora_utc()),
                "registrado_por": getattr(staff, "id", None),
            })
            self._salvar()

        await self._atualizar_mensagem_partida(guild, partida, f"🏁 Resultado registrado: **Time {vencedor + 1}** venceu.")
        await self._sincronizar_cargos(guild, ids)
        await self._atualizar_painel(guild)
        return True

    async def cancelar_partida(self, guild: discord.Guild, partida: dict, staff, motivo: str = "cancelada pela staff") -> bool:
        async with self._lock:
            if partida["status"] != "aberta":
                return False
            partida["status"] = "cancelada"
            partida["finalizada_em"] = _iso(agora_utc())
            partida["registrado_por"] = getattr(staff, "id", None)
            self._salvar()
        await self._atualizar_mensagem_partida(guild, partida, f"🚫 Partida {motivo}. Ninguém perdeu nem ganhou MMR.")
        await self._atualizar_painel(guild)
        return True

    async def desfazer_partida(self, guild: discord.Guild, partida: dict) -> bool:
        """Reverte o resultado registrado e reabre a partida pra staff registrar de novo."""
        async with self._lock:
            if partida["status"] != "finalizada":
                return False
            modo = partida["modo"]
            perfis = ler("perfis")
            for u in todos_jogadores(partida):
                d = self._dados_modo(perfis, u, modo, guild.get_member(u))
                d["mmr"] = max(0, d["mmr"] - partida["deltas"][str(u)])
                d["jogos"] = max(0, d["jogos"] - 1)
                chave = "vitorias" if u in partida["times"][partida["vencedor"]] else "derrotas"
                d[chave] = max(0, d[chave] - 1)
            salvar("perfis", perfis)
            for k in ("vencedor", "deltas", "promocoes", "finalizada_em", "registrado_por"):
                partida.pop(k, None)
            partida["status"] = "aberta"
            self._salvar()
        await self._atualizar_mensagem_partida(guild, partida, "↩️ Resultado desfeito. A partida foi reaberta — a staff pode registrar de novo.")
        await self._sincronizar_cargos(guild, todos_jogadores(partida))
        await self._atualizar_painel(guild)
        return True

    async def _atualizar_mensagem_partida(self, guild: discord.Guild, partida: dict, aviso: str):
        canal = self._canal()
        if canal is None or not partida.get("msg_id"):
            return
        aberta = partida["status"] == "aberta"
        try:
            await canal.get_partial_message(int(partida["msg_id"])).edit(
                embed=self._embed_partida(partida),
                view=ResultadoView(self) if aberta else None,
            )
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui editar a mensagem da partida #{partida['id']}: {e}")
        if partida.get("thread_id"):
            try:
                thread = guild.get_thread(int(partida["thread_id"])) or await guild.fetch_channel(int(partida["thread_id"]))
                await thread.edit(archived=False, locked=False)
                await thread.send(aviso)
                if not aberta:
                    await thread.edit(archived=True, locked=True)
            except discord.HTTPException as e:
                print(f"[INTERNO] ⚠️ Não consegui atualizar a thread da partida #{partida['id']}: {e}")

    # ── cargos de tier ──────────────────────────────────────────────────
    @staticmethod
    def _nome_cargo(nome: str, emoji: str) -> str:
        return f"{emoji} Interno {nome}"

    async def _garantir_cargos(self, guild: discord.Guild) -> dict:
        ids = self.cfg.setdefault("cargos", {})
        roles = {}
        for _, nome, emoji, cor in TIERS:
            role = guild.get_role(ids.get(nome, 0)) or discord.utils.get(guild.roles, name=self._nome_cargo(nome, emoji))
            if role is None:
                role = await guild.create_role(
                    name=self._nome_cargo(nome, emoji),
                    colour=discord.Colour(cor),
                    mentionable=False,
                    reason="Amistoso interno: cargo de tier",
                )
            ids[nome] = role.id
            roles[nome] = role
        self._salvar()
        return roles

    async def _sincronizar_cargos(self, guild: discord.Guild, uids: list):
        if not self.cfg.get("cargos"):
            return
        try:
            roles = await self._garantir_cargos(guild)
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui garantir os cargos de tier: {e}")
            return
        perfis = ler("perfis")
        for uid in uids:
            membro = guild.get_member(uid)
            if membro is None:
                continue
            tier = self.tier_geral(perfis, uid)
            desejado = roles[tier[0]] if tier else None
            try:
                for nome, role in roles.items():
                    if role in membro.roles and role != desejado:
                        await membro.remove_roles(role, reason="Interno: mudou de tier")
                if desejado is not None and desejado not in membro.roles:
                    await membro.add_roles(desejado, reason="Interno: novo tier")
            except discord.HTTPException as e:
                print(f"[INTERNO] ⚠️ Não consegui atualizar o cargo de {membro}: {e}")

    # ── rank de um jogador ──────────────────────────────────────────────
    def embed_rank(self, membro) -> discord.Embed:
        perfis = ler("perfis")
        interno = perfis.get(str(membro.id), {}).get("interno", {})
        emb = discord.Embed(title=f"📊 Rank interno de {membro.display_name}", color=0xD4A843)
        emb.set_thumbnail(url=membro.display_avatar.url)
        geral = self.tier_geral(perfis, membro.id)
        emb.description = f"{geral[1]} **{geral[0]}**" if geral else "🧪 _Ainda em calibragem — jogue mais partidas pra aparecer o tier._"
        for modo in MODOS:
            d = interno.get(modo)
            if not d or d.get("jogos", 0) == 0:
                emb.add_field(name=modo, value="_sem partidas_", inline=True)
                continue
            jogos = d["jogos"]
            wr = round(d["vitorias"] / jogos * 100)
            if jogos >= PARTIDAS_CALIBRAGEM:
                nome, emoji, _ = tier_para_mmr(d["mmr"])
                topo = f"`{d['mmr']}` MMR • {emoji} {nome}"
            else:
                topo = f"`{d['mmr']}` MMR • 🧪 calibrando ({jogos}/{PARTIDAS_CALIBRAGEM})"
            emb.add_field(name=modo, value=f"{topo}\n`{d['vitorias']}V {d['derrotas']}D` • {wr}%", inline=True)
        return emb

    # ═════════════════════════════════════════════════════════════════════
    #  Manutenção automática
    # ═════════════════════════════════════════════════════════════════════
    @tasks.loop(minutes=1)
    async def tick(self):
        try:
            mudou_fila = False
            limite = agora_utc() - timedelta(minutes=FILA_TIMEOUT_MIN)
            async with self._lock:
                for modo in MODOS:
                    fila = self.estado["filas"][modo]
                    novo = [e for e in fila if _dt(e["t"]) > limite]
                    if len(novo) != len(fila):
                        self.estado["filas"][modo] = novo
                        mudou_fila = True
                if mudou_fila:
                    self._salvar()
            if mudou_fila:
                await self._atualizar_painel()

            expiradas = [
                p for p in self.estado["partidas"].values()
                if p["status"] == "aberta" and _dt(p["criada_em"]) < agora_utc() - timedelta(hours=PARTIDA_EXPIRA_H)
            ]
            for p in expiradas:
                canal = self._canal()
                if canal is not None:
                    await self.cancelar_partida(canal.guild, p, None, motivo=f"expirada (sem resultado em {PARTIDA_EXPIRA_H}h)")
        except Exception as e:
            print(f"[INTERNO] ❌ Erro na manutenção automática: {e}")

    @tick.before_loop
    async def _antes_tick(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_remove(self, membro: discord.Member):
        mexeu = False
        async with self._lock:
            for modo in MODOS:
                fila = self.estado["filas"][modo]
                novo = [e for e in fila if e["id"] != membro.id]
                if len(novo) != len(fila):
                    self.estado["filas"][modo] = novo
                    mexeu = True
            if mexeu:
                self._salvar()
        if mexeu:
            await self._atualizar_painel(membro.guild)

    # ═════════════════════════════════════════════════════════════════════
    #  Comandos
    # ═════════════════════════════════════════════════════════════════════
    async def _exigir_staff(self, interaction: discord.Interaction) -> bool:
        if self._eh_staff(interaction.user):
            return True
        await interaction.response.send_message("🚫 Só a staff pode usar esse comando.", ephemeral=True)
        return False

    def _achar_partida(self, numero: int) -> Optional[dict]:
        return self.estado["partidas"].get(str(numero))

    @interno.command(name="setup", description="[Staff] Cria os cargos de tier e posta o painel de fila.")
    @app_commands.describe(canal="Canal onde o painel de fila e as partidas vão aparecer")
    async def setup_cmd(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if not isinstance(interaction.user, discord.Member) or not (
            interaction.user.guild_permissions.administrator or eh_super_admin_membro(interaction.user)
        ):
            await interaction.response.send_message("🚫 Só administradores podem usar esse comando.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        avisos = []
        try:
            await self._garantir_cargos(interaction.guild)
        except discord.HTTPException as e:
            avisos.append(f"⚠️ Não consegui criar os cargos de tier ({e}). Dê **Gerenciar Cargos** ao bot.")
        try:
            msg = await canal.send(embed=self._embed_painel(), view=PainelView(self))
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Não consegui postar o painel em {canal.mention}: {e}", ephemeral=True)
            return
        async with self._lock:
            self.cfg["canal_id"] = canal.id
            self.cfg["painel_msg_id"] = msg.id
            self._salvar()
        await interaction.followup.send(
            f"✅ Painel do **Amistoso Interno** postado em {canal.mention}.\n" + "\n".join(avisos), ephemeral=True
        )

    @interno.command(name="rank", description="Veja o MMR e o tier interno de um jogador.")
    @app_commands.describe(membro="Jogador (deixe vazio pra ver o seu)")
    async def rank_cmd(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        await interaction.response.send_message(embed=self.embed_rank(membro or interaction.user))

    @interno.command(name="sair", description="Sai de todas as filas do amistoso interno.")
    async def sair_cmd(self, interaction: discord.Interaction):
        await self.sair_das_filas(interaction)

    @interno.command(name="pendentes", description="[Staff] Lista as partidas aguardando resultado.")
    async def pendentes_cmd(self, interaction: discord.Interaction):
        if not await self._exigir_staff(interaction):
            return
        abertas = [p for p in self.estado["partidas"].values() if p["status"] == "aberta"]
        if not abertas:
            await interaction.response.send_message("✅ Nenhuma partida aguardando resultado.", ephemeral=True)
            return
        linhas = []
        for p in sorted(abertas, key=lambda p: p["id"]):
            t1 = " ".join(f"<@{u}>" for u in p["times"][0])
            t2 = " ".join(f"<@{u}>" for u in p["times"][1])
            quando = discord.utils.format_dt(_dt(p["criada_em"]), "R")
            linhas.append(f"**#{p['id']}** ({p['modo']}) {quando}\n🔵 {t1}\n🟠 {t2}")
        await interaction.response.send_message("\n\n".join(linhas)[:1900], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @interno.command(name="resultado", description="[Staff] Registra o vencedor de uma partida.")
    @app_commands.describe(partida="Número da partida", vencedor="Qual time venceu")
    @app_commands.choices(vencedor=[
        app_commands.Choice(name="🔵 Time 1", value=1),
        app_commands.Choice(name="🟠 Time 2", value=2),
    ])
    async def resultado_cmd(self, interaction: discord.Interaction, partida: int, vencedor: app_commands.Choice[int]):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar_partida(partida)
        if p is None or p["status"] != "aberta":
            await interaction.response.send_message("❌ Partida não encontrada ou já finalizada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.finalizar_partida(interaction.guild, p, vencedor.value - 1, interaction.user)
        await interaction.followup.send(f"✅ Partida #{partida} registrada: **Time {vencedor.value}** venceu.", ephemeral=True)

    @interno.command(name="cancelar", description="[Staff] Cancela uma partida aberta (sem mexer no MMR).")
    @app_commands.describe(partida="Número da partida")
    async def cancelar_cmd(self, interaction: discord.Interaction, partida: int):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar_partida(partida)
        if p is None or p["status"] != "aberta":
            await interaction.response.send_message("❌ Partida não encontrada ou já finalizada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.cancelar_partida(interaction.guild, p, interaction.user)
        await interaction.followup.send(f"🚫 Partida #{partida} cancelada.", ephemeral=True)

    @interno.command(name="desfazer", description="[Staff] Desfaz o resultado de uma partida e reabre ela.")
    @app_commands.describe(partida="Número da partida")
    async def desfazer_cmd(self, interaction: discord.Interaction, partida: int):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar_partida(partida)
        if p is None or p["status"] != "finalizada":
            await interaction.response.send_message("❌ Partida não encontrada ou sem resultado registrado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.desfazer_partida(interaction.guild, p)
        await interaction.followup.send(f"↩️ Resultado da partida #{partida} desfeito. Ela foi reaberta.", ephemeral=True)

    @interno.command(name="ajustar-mmr", description="[Staff] Define o MMR de um jogador num modo.")
    @app_commands.describe(membro="Jogador", modo="Modo", valor="Novo MMR (0 a 3000)")
    @app_commands.choices(modo=[app_commands.Choice(name=m, value=m) for m in MODOS])
    async def ajustar_cmd(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        modo: app_commands.Choice[str],
        valor: app_commands.Range[int, 0, 3000],
    ):
        if not await self._exigir_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        async with self._lock:
            perfis = ler("perfis")
            d = self._dados_modo(perfis, membro.id, modo.value, membro)
            antes = d["mmr"]
            d["mmr"] = valor
            salvar("perfis", perfis)
        await self._sincronizar_cargos(interaction.guild, [membro.id])
        await interaction.followup.send(
            f"✅ MMR de {membro.mention} em **{modo.value}**: `{antes}` → `{valor}`.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Interno(bot))
