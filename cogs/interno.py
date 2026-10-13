import asyncio
import secrets
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs import mod_utils as mu
from cogs.backup import ler, salvar
from cogs.friendly import (
    AMISTOSOS_CHANNEL_ID,
    CATEGORIA_VOZ_AMISTOSOS_ID,
    DIAS_SEMANA,
    _calcular_data_hora,
    extrair_cargos_extras,
    montar_ranks_display,
    rank_info,
)
from cogs.json_store import ler_json, salvar_json
from cogs.mod_utils import eh_super_admin_membro
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────────────────────────────────
#  Cog: Amistoso Interno
#  Arquivo: cogs/interno.py
#
#  Mesma lógica do /amistoso, mas entre os próprios membros do clube
#  (1v1, 2v2 ou 3v3):
#
#   1. A staff usa  /interno modo:2v2 [dia] [horário] [ranks]  e o bot
#      anuncia no canal de amistosos, com os botões Entrar / Sair.
#   2. Os jogadores entram pelo botão. Os times se formam PELA ORDEM DE
#      ENTRADA: os primeiros N são o Time 1 e os N seguintes, o Time 2.
#   3. Quando lota, o bot cria um canal de texto privado e uma call pra
#      cada time, e mostra os times, o nome e a senha da sala.
#   4. Depois do jogo, a STAFF diz quem ganhou (botões no canal da partida
#      ou /interno-resultado). O bot divulga o resultado, soma vitória/derrota
#      no /perfil de cada um, leva todo mundo da call pro lobby e apaga os
#      canais.
#
#  Outros comandos da staff: /interno-cancelar e /interno-desfazer.
#
#  Dados: data/interno.json (partidas) e data/perfis.json -> perfil["interno"]
#  [modo] = {vitorias, derrotas}. Não mexe nos números dos amistosos
#  contra outros times.
#
#  PERMISSÕES DO BOT: Gerenciar Canais, Gerenciar Cargos/Permissões (pra criar
#  canais privados), Mover Membros e Enviar Mensagens/Incorporar Links.
# ─────────────────────────────────────────────────────────────────────────

ARQUIVO = "data/interno.json"

MODOS = {"1v1": 1, "2v2": 2, "3v3": 3}      # jogadores por time
EMOJI_TIME = {0: "🔵", 1: "🟠"}
ATRASO_APAGAR_CANAIS = 3                    # segundos (igual ao /resultado do amistoso)


# ═════════════════════════════════════════════════════════════════════════
#  Funções puras (sem Discord) — fáceis de testar
# ═════════════════════════════════════════════════════════════════════════

def agora_str_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def montar_times(jogadores: list, por_time: int):
    """Times pela ORDEM DE ENTRADA: os primeiros `por_time` são o Time 1,
    os seguintes são o Time 2."""
    return list(jogadores[:por_time]), list(jogadores[por_time:por_time * 2])


def estado_padrao() -> dict:
    return {"contador": 0, "partidas": {}}


def carregar_estado() -> dict:
    bruto = ler_json(ARQUIVO, dict)
    estado = estado_padrao()
    if isinstance(bruto, dict):
        estado["contador"] = int(bruto.get("contador", 0))
        # ignora partidas de versões antigas do sistema (sem a lista de jogadores)
        estado["partidas"] = {
            k: p for k, p in (bruto.get("partidas") or {}).items()
            if isinstance(p, dict) and "jogadores" in p
        }
    return estado


def todos_jogadores(p: dict) -> list:
    if p.get("times"):
        return [u for time in p["times"] for u in time]
    return list(p["jogadores"])


# ═════════════════════════════════════════════════════════════════════════
#  Views persistentes (os botões continuam funcionando depois de reiniciar)
# ═════════════════════════════════════════════════════════════════════════

class EntrarView(discord.ui.View):
    """Botões do anúncio. A partida é descoberta pelo ID da mensagem clicada."""

    def __init__(self, cog: "Interno"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="✅  Entrar", style=discord.ButtonStyle.success, custom_id="interno:entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clique_entrar(interaction)

    @discord.ui.button(label="🚪  Sair", style=discord.ButtonStyle.danger, custom_id="interno:sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clique_sair(interaction)


class ResultadoView(discord.ui.View):
    """Botões da staff no canal da partida (a partida é descoberta pelo ID do canal)."""

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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.estado = carregar_estado()
        self._lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(EntrarView(self))
        self.bot.add_view(ResultadoView(self))

    # ── atalhos ─────────────────────────────────────────────────────────
    def _salvar(self):
        salvar_json(ARQUIVO, self.estado)

    def _eh_staff(self, membro) -> bool:
        if not isinstance(membro, discord.Member):
            return False
        if membro.guild_permissions.administrator or eh_super_admin_membro(membro):
            return True
        return any(r.id in STAFF_IDS for r in membro.roles)

    def _canal_anuncio(self) -> Optional[discord.TextChannel]:
        c = self.bot.get_channel(AMISTOSOS_CHANNEL_ID)
        return c if isinstance(c, discord.TextChannel) else None

    def _partida_por_msg(self, msg_id: int) -> Optional[dict]:
        return next((p for p in self.estado["partidas"].values() if p.get("msg_id") == msg_id), None)

    def _partida_por_canal(self, canal_id: int) -> Optional[dict]:
        return next((p for p in self.estado["partidas"].values() if p.get("canal_id") == canal_id), None)

    def _partida_em_andamento_de(self, uid: int) -> Optional[dict]:
        for p in self.estado["partidas"].values():
            if p["status"] == "andamento" and uid in todos_jogadores(p):
                return p
        return None

    # ── perfil: vitórias/derrotas por modo ──────────────────────────────
    @staticmethod
    def _stats_modo(perfis: dict, uid: int, modo: str, membro=None) -> dict:
        sid = str(uid)
        if sid not in perfis:
            perfis[sid] = {
                "nome": getattr(membro, "display_name", str(uid)),
                "amistosos": 0, "vitorias": 0, "derrotas": 0,
            }
        dados = perfis[sid]
        dados.setdefault("amistosos", 0)
        dados.setdefault("vitorias", 0)
        dados.setdefault("derrotas", 0)
        interno = dados.setdefault("interno", {})
        d = interno.setdefault(modo, {})
        d.setdefault("vitorias", 0)
        d.setdefault("derrotas", 0)
        return d

    # ═════════════════════════════════════════════════════════════════════
    #  Anúncio
    # ═════════════════════════════════════════════════════════════════════
    def _linhas_time(self, p: dict, idx: int) -> str:
        por_time = p["por_time"]
        if p.get("times"):
            jogadores = p["times"][idx]
        else:
            jogadores = p["jogadores"][idx * por_time:(idx + 1) * por_time]
        linhas = [f"  ▸  <@{u}>" for u in jogadores]
        linhas += ["  ▸  _vaga livre_"] * (por_time - len(jogadores))
        return "\n".join(linhas)

    def _embed_anuncio(self, p: dict) -> discord.Embed:
        status = p["status"]
        titulo = {
            "aberta": f"⚔️  AMISTOSO INTERNO — {p['modo']}",
            "andamento": f"🎮  INTERNO #{p['id']} — {p['modo']} • em andamento",
            "finalizada": f"✅  INTERNO #{p['id']} — {p['modo']} • finalizado",
            "cancelada": f"🚫  INTERNO #{p['id']} — {p['modo']} • cancelado",
        }.get(status, f"INTERNO #{p['id']}")
        cor = {"aberta": 0xD4A843, "andamento": 0xE67E22, "finalizada": 0x2ECC71, "cancelada": 0x95A5A6}.get(status, 0xD4A843)
        emb = discord.Embed(title=titulo, color=cor, timestamp=datetime.now(timezone.utc))
        emb.add_field(name="🎮  Modo", value=f"**{p['modo']}**", inline=True)
        emb.add_field(name="📅  Data / Hora", value=f"**{p['data_hora']}**", inline=True)
        if p.get("rank_display"):
            emb.add_field(name="🏅  Rank", value=p["rank_display"], inline=True)
        if p.get("info"):
            emb.add_field(name="📝  Informações", value=p["info"], inline=False)

        for i in (0, 1):
            vencedor = " 🏆" if status == "finalizada" and p.get("vencedor") == i else ""
            ocupados = len(p["times"][i]) if p.get("times") else len(p["jogadores"][i * p["por_time"]:(i + 1) * p["por_time"]])
            emb.add_field(
                name=f"{EMOJI_TIME[i]}  Time {i + 1}{vencedor}  `({ocupados}/{p['por_time']})`",
                value=self._linhas_time(p, i),
                inline=True,
            )

        if status == "aberta":
            total = p["por_time"] * 2
            emb.add_field(
                name="​",
                value=(
                    f"{p.get('mencao', '')}\n" if p.get("mencao") else ""
                ) + (
                    f"Clique em **✅ Entrar**. Os times se formam **pela ordem de entrada**: os "
                    f"{p['por_time']} primeiros são o Time 1 e os {p['por_time']} seguintes, o Time 2.\n"
                    f"Quando lotar ({len(p['jogadores'])}/{total}), o bot cria o canal e a call da partida."
                ),
                inline=False,
            )
        elif status == "andamento":
            emb.add_field(
                name="​",
                value=f"📁 Canal: <#{p['canal_id']}>\n🔊 Calls: " + " • ".join(f"<#{v}>" for v in p["voz_ids"]),
                inline=False,
            )
        emb.set_footer(text=f"Interno #{p['id']} • anunciado por {p.get('criada_por_nome', 'staff')}")
        return emb

    async def _atualizar_anuncio(self, p: dict):
        canal = self._canal_anuncio()
        if canal is None or not p.get("msg_id"):
            return
        try:
            await canal.get_partial_message(int(p["msg_id"])).edit(
                embed=self._embed_anuncio(p),
                view=EntrarView(self) if p["status"] == "aberta" else None,
            )
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui atualizar o anúncio do interno #{p['id']}: {e}")

    # ═════════════════════════════════════════════════════════════════════
    #  Entrar / sair
    # ═════════════════════════════════════════════════════════════════════
    async def clique_entrar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        membro, guild = interaction.user, interaction.guild
        iniciou = None
        async with self._lock:
            p = self._partida_por_msg(interaction.message.id)
            if p is None or p["status"] != "aberta":
                await interaction.followup.send("⚠️ As inscrições desse interno já foram encerradas.", ephemeral=True)
                return
            if p["rank_ids"] and not any(r.id in p["rank_ids"] for r in membro.roles):
                await interaction.followup.send(
                    f"❌ Apenas jogadores **{p['rank_display']}** podem entrar neste interno.", ephemeral=True
                )
                return
            if membro.id in p["jogadores"]:
                await interaction.followup.send("⚠️ Você já está nesse interno!", ephemeral=True)
                return
            outra = self._partida_em_andamento_de(membro.id)
            if outra:
                await interaction.followup.send(
                    f"⏳ Você ainda está no **interno #{outra['id']}** (em andamento). Termine ele antes de entrar em outro.",
                    ephemeral=True,
                )
                return

            p["jogadores"].append(membro.id)
            total = p["por_time"] * 2
            try:
                if len(p["jogadores"]) >= total:
                    await self._iniciar_partida(guild, p)
                    iniciou = p
            except (discord.HTTPException, RuntimeError) as e:
                p["jogadores"].remove(membro.id)
                self._salvar()
                await interaction.followup.send(
                    f"❌ Não consegui criar o canal da partida ({e}). Avise a staff — o bot precisa de **Gerenciar Canais**.",
                    ephemeral=True,
                )
                return
            self._salvar()

        await self._atualizar_anuncio(p)
        if iniciou:
            await interaction.followup.send(
                f"🎮 Interno lotado! Sua partida: <#{p['canal_id']}> 🚀", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Você entrou no interno ({len(p['jogadores'])}/{p['por_time'] * 2}). Quando lotar, te marco no canal da partida!",
                ephemeral=True,
            )

    async def clique_sair(self, interaction: discord.Interaction):
        async with self._lock:
            p = self._partida_por_msg(interaction.message.id)
            if p is None or p["status"] != "aberta":
                await interaction.response.send_message("⚠️ Esse interno já não aceita saídas.", ephemeral=True)
                return
            if interaction.user.id not in p["jogadores"]:
                await interaction.response.send_message("ℹ️ Você não está nesse interno.", ephemeral=True)
                return
            p["jogadores"].remove(interaction.user.id)
            self._salvar()
        await interaction.response.send_message("🚪 Você saiu do interno.", ephemeral=True)
        await self._atualizar_anuncio(p)

    @commands.Cog.listener()
    async def on_member_remove(self, membro: discord.Member):
        mexidas = []
        async with self._lock:
            for p in self.estado["partidas"].values():
                if p["status"] == "aberta" and membro.id in p["jogadores"]:
                    p["jogadores"].remove(membro.id)
                    mexidas.append(p)
            if mexidas:
                self._salvar()
        for p in mexidas:
            await self._atualizar_anuncio(p)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Anúncio apagado antes de lotar = interno cancelado (igual ao amistoso)."""
        if payload.channel_id != AMISTOSOS_CHANNEL_ID:
            return
        async with self._lock:
            p = self._partida_por_msg(payload.message_id)
            if p is None or p["status"] != "aberta":
                return
            p["status"] = "cancelada"
            p["finalizada_em"] = agora_str_iso()
            self._salvar()

    # ═════════════════════════════════════════════════════════════════════
    #  Criação dos canais quando lota
    # ═════════════════════════════════════════════════════════════════════
    @staticmethod
    def _ow_membros(guild: discord.Guild, ids: list, voz: bool) -> dict:
        def perm():
            if voz:
                return discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
            return discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ow = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False) if voz
            else discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True, manage_channels=True),
        }
        for rid in STAFF_IDS:
            role = guild.get_role(rid)
            if role:
                ow[role] = perm()
        for uid in ids:
            membro = guild.get_member(uid)
            if membro:
                ow[membro] = perm()
        return ow

    async def _criar_canais(self, guild: discord.Guild, p: dict):
        """Cria o canal de texto da partida e uma call por time. Se algo falhar
        no meio, apaga o que já criou pra não deixar canal órfão."""
        ref = guild.get_channel(AMISTOSOS_CHANNEL_ID)
        categoria = ref.category if ref else None
        categoria_voz = guild.get_channel(CATEGORIA_VOZ_AMISTOSOS_ID)
        criados, vozes = [], []
        try:
            texto = await guild.create_text_channel(
                name=f"interno-{p['id']}-{p['modo']}",
                overwrites=self._ow_membros(guild, todos_jogadores(p), voz=False),
                category=categoria,
                reason=f"Interno #{p['id']} ({p['modo']}) lotou",
            )
            criados.append(texto)
            for i, time in enumerate(p["times"]):
                voz = await guild.create_voice_channel(
                    name=f"{EMOJI_TIME[i]}│Interno #{p['id']} Time {i + 1}"[:100],
                    overwrites=self._ow_membros(guild, time, voz=True),
                    category=categoria_voz,
                    reason=f"Call do Time {i + 1} do interno #{p['id']}",
                )
                criados.append(voz)
                vozes.append(voz)
        except Exception:
            for c in criados:
                try:
                    await c.delete(reason="Interno: falha ao montar a partida")
                except discord.HTTPException:
                    pass
            raise
        return texto, vozes

    async def _iniciar_partida(self, guild: discord.Guild, p: dict):
        t1, t2 = montar_times(p["jogadores"], p["por_time"])
        p["times"] = [t1, t2]
        try:
            texto, vozes = await self._criar_canais(guild, p)
        except Exception:
            p.pop("times", None)
            raise
        p["canal_id"] = texto.id
        p["voz_ids"] = [v.id for v in vozes]
        p["sala"] = {"nome": f"TH{p['id']:04d}", "senha": f"{secrets.randbelow(10000):04d}"}
        p["status"] = "andamento"

        mencoes = " ".join(f"<@{u}>" for u in todos_jogadores(p))
        emb = discord.Embed(
            title=f"🎮  Interno #{p['id']} — {p['modo']}",
            description="Times formados pela ordem de entrada. Boa partida! 🚀",
            color=0xE67E22,
        )
        for i in (0, 1):
            emb.add_field(
                name=f"{EMOJI_TIME[i]}  Time {i + 1}",
                value="\n".join(f"  ▸  <@{u}>" for u in p["times"][i]) + f"\n🔊 <#{p['voz_ids'][i]}>",
                inline=True,
            )
        emb.add_field(
            name="🏟️  Sala (partida privada)",
            value=f"Nome: `{p['sala']['nome']}` • Senha: ||`{p['sala']['senha']}`||\nO **Time 1** cria a sala e o **Time 2** entra.",
            inline=False,
        )
        emb.add_field(
            name="​",
            value="Quando acabar, **a staff registra quem ganhou** pelos botões abaixo.",
            inline=False,
        )
        try:
            await texto.send(
                mencoes, embed=emb, view=ResultadoView(self),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException as e:
            print(f"[INTERNO] ⚠️ Não consegui postar a mensagem no canal da partida #{p['id']}: {e}")
        print(f"[INTERNO] 🎮 Interno #{p['id']} ({p['modo']}) lotou: {p['times']}")

    # ═════════════════════════════════════════════════════════════════════
    #  Resultado (somente staff)
    # ═════════════════════════════════════════════════════════════════════
    async def clique_resultado(self, interaction: discord.Interaction, vencedor: Optional[int]):
        if not self._eh_staff(interaction.user):
            await interaction.response.send_message("🚫 Só a staff registra o resultado.", ephemeral=True)
            return
        p = self._partida_por_canal(interaction.channel.id)
        if p is None or p["status"] != "andamento":
            await interaction.response.send_message("ℹ️ Essa partida não está mais em andamento.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if vencedor is None:
            ok = await self.cancelar(interaction.guild, p, interaction.user)
            texto = f"🚫 Interno #{p['id']} cancelado." if ok else "ℹ️ Essa partida não está mais em andamento."
        else:
            ok = await self.finalizar(interaction.guild, p, vencedor, interaction.user)
            texto = f"✅ Interno #{p['id']} registrado: **Time {vencedor + 1}** venceu." if ok else "ℹ️ Essa partida não está mais em andamento."
        try:
            await interaction.followup.send(texto, ephemeral=True)
        except discord.HTTPException:
            pass  # o canal pode já ter sido apagado

    async def finalizar(self, guild: discord.Guild, p: dict, vencedor: int, staff) -> bool:
        async with self._lock:
            if p["status"] != "andamento":
                return False
            perfis = ler("perfis")
            for i, time in enumerate(p["times"]):
                for u in time:
                    d = self._stats_modo(perfis, u, p["modo"], guild.get_member(u))
                    d["vitorias" if i == vencedor else "derrotas"] += 1
            salvar("perfis", perfis)
            p["status"] = "finalizada"
            p["vencedor"] = vencedor
            p["finalizada_em"] = agora_str_iso()
            p["registrado_por"] = getattr(staff, "id", None)
            self._salvar()
        await self._atualizar_anuncio(p)
        await self._anunciar_resultado(p)
        await self._apagar_canais(guild, p, "resultado registrado")
        return True

    async def cancelar(self, guild: discord.Guild, p: dict, staff) -> bool:
        async with self._lock:
            if p["status"] not in ("aberta", "andamento"):
                return False
            tinha_canais = p["status"] == "andamento"
            p["status"] = "cancelada"
            p["finalizada_em"] = agora_str_iso()
            p["registrado_por"] = getattr(staff, "id", None)
            self._salvar()
        await self._atualizar_anuncio(p)
        if tinha_canais:
            await self._apagar_canais(guild, p, "partida cancelada")
        return True

    async def desfazer(self, guild: discord.Guild, p: dict) -> bool:
        """Tira as vitórias/derrotas de um resultado registrado por engano.
        (Os canais já foram apagados, então a partida não reabre.)"""
        async with self._lock:
            if p["status"] != "finalizada":
                return False
            perfis = ler("perfis")
            for i, time in enumerate(p["times"]):
                for u in time:
                    d = self._stats_modo(perfis, u, p["modo"], guild.get_member(u))
                    chave = "vitorias" if i == p["vencedor"] else "derrotas"
                    d[chave] = max(0, d[chave] - 1)
            salvar("perfis", perfis)
            p["status"] = "desfeita"
            self._salvar()
        canal = self._canal_anuncio()
        if canal and p.get("msg_id"):
            try:
                await canal.get_partial_message(int(p["msg_id"])).edit(
                    embed=discord.Embed(
                        title=f"↩️  INTERNO #{p['id']} — {p['modo']} • resultado desfeito",
                        description="A staff desfez o resultado desta partida. Nada foi somado ao perfil.",
                        color=0x95A5A6,
                    ),
                    view=None,
                )
            except discord.HTTPException:
                pass
        return True

    async def _anunciar_resultado(self, p: dict):
        canal = self._canal_anuncio()
        if canal is None:
            return
        v = p["vencedor"]
        perdedor = 1 - v
        emb = discord.Embed(
            title=f"🏆  Interno #{p['id']} ({p['modo']}) — Time {v + 1} venceu!",
            color=0x2ECC71,
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(name=f"{EMOJI_TIME[v]}  Time {v + 1} 🏆", value="\n".join(f"  ▸  <@{u}>" for u in p["times"][v]), inline=True)
        emb.add_field(name=f"{EMOJI_TIME[perdedor]}  Time {perdedor + 1}", value="\n".join(f"  ▸  <@{u}>" for u in p["times"][perdedor]), inline=True)
        sem_ping = discord.AllowedMentions.none()
        try:
            msg = await canal.fetch_message(int(p["msg_id"]))
            await msg.reply(embed=emb, allowed_mentions=sem_ping)
        except (discord.NotFound, discord.HTTPException):
            try:
                await canal.send(embed=emb, allowed_mentions=sem_ping)
            except discord.HTTPException as e:
                print(f"[INTERNO] ⚠️ Não consegui divulgar o resultado do interno #{p['id']}: {e}")

    async def _apagar_canais(self, guild: discord.Guild, p: dict, motivo: str):
        """Igual ao /resultado do amistoso: avisa, espera uns segundos, apaga o canal
        de texto, leva o pessoal da call pro lobby e apaga as calls."""
        texto = guild.get_channel(p["canal_id"]) if p.get("canal_id") else None
        if texto is not None:
            try:
                await texto.send(f"🏁 Interno #{p['id']} encerrado ({motivo}). Este canal será apagado em instantes!")
            except discord.HTTPException:
                pass
            await asyncio.sleep(ATRASO_APAGAR_CANAIS)
            try:
                await texto.delete(reason=f"Interno #{p['id']} encerrado — {motivo}.")
            except discord.HTTPException as e:
                print(f"[INTERNO] ⚠️ Erro ao apagar o canal do interno #{p['id']}: {e}")
        for vid in p.get("voz_ids", []):
            voz = guild.get_channel(vid)
            if voz is None:
                continue
            try:
                await mu.mover_membros_pos_amistoso(self.bot, voz)
            except Exception as e:
                print(f"[INTERNO] ⚠️ Erro ao mover o pessoal da call pro lobby: {e}")
            try:
                await voz.delete(reason=f"Interno #{p['id']} encerrado — {motivo}.")
            except discord.HTTPException as e:
                print(f"[INTERNO] ⚠️ Erro ao apagar a call do interno #{p['id']}: {e}")
        async with self._lock:
            p["canal_id"] = None
            p["voz_ids"] = []
            self._salvar()

    # ═════════════════════════════════════════════════════════════════════
    #  Comandos (staff)
    # ═════════════════════════════════════════════════════════════════════
    async def _exigir_staff(self, interaction: discord.Interaction) -> bool:
        if self._eh_staff(interaction.user):
            return True
        await interaction.response.send_message("❌ Apenas a **staff** pode usar esse comando.", ephemeral=True)
        return False

    @app_commands.command(name="interno", description="[Staff] Anuncia um amistoso interno (1v1, 2v2 ou 3v3) entre os membros.")
    @app_commands.describe(
        modo="Formato da partida",
        dia_semana="Dia (opcional)",
        horario="Horário, ex: 20h00 (opcional)",
        rank1="Só deixa entrar quem tem esse cargo de rank (opcional)",
        rank2="Segundo cargo de rank (opcional)",
        rank3="Terceiro cargo de rank (opcional)",
        mais_cargos="Mais cargos (opcional): marque com @ ou cole os IDs, separados por espaço",
        info_extra="Informações extras (opcional)",
    )
    @app_commands.choices(
        modo=[app_commands.Choice(name=m, value=m) for m in MODOS],
        dia_semana=[app_commands.Choice(name=d, value=d) for d in DIAS_SEMANA],
    )
    async def interno(
        self,
        interaction: discord.Interaction,
        modo: app_commands.Choice[str],
        dia_semana: Optional[app_commands.Choice[str]] = None,
        horario: str = "",
        rank1: Optional[discord.Role] = None,
        rank2: Optional[discord.Role] = None,
        rank3: Optional[discord.Role] = None,
        mais_cargos: str = "",
        info_extra: str = "",
    ):
        if not await self._exigir_staff(interaction):
            return
        guild = interaction.guild
        canal = self._canal_anuncio()
        if canal is None:
            await interaction.response.send_message("❌ Canal de amistosos não encontrado.", ephemeral=True)
            return
        outros, erro = extrair_cargos_extras(guild, mais_cargos)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        ranks_ids = []
        for cargo in [rank1, rank2, rank3, *outros]:
            if cargo is None or cargo.id in ranks_ids:
                continue
            if rank_info(cargo) is None:
                await interaction.followup.send(f"❌ O cargo {cargo.mention} não é um rank válido.", ephemeral=True)
                return
            ranks_ids.append(cargo.id)

        rank_display, mencao = "", ""
        if ranks_ids:
            nomes, emojis = montar_ranks_display(ranks_ids)
            rank_display = " + ".join(f"{e} {n}" for e, n in zip(emojis, nomes))
            mencao = " ".join(guild.get_role(rid).mention for rid in ranks_ids if guild.get_role(rid))

        if dia_semana is None and not horario.strip():
            data_hora = "Assim que lotar"
        else:
            data_hora, _ = _calcular_data_hora(dia_semana.value if dia_semana else "Hoje", horario)

        async with self._lock:
            self.estado["contador"] += 1
            pid = self.estado["contador"]
            p = {
                "id": pid,
                "modo": modo.value,
                "por_time": MODOS[modo.value],
                "status": "aberta",
                "jogadores": [],
                "rank_ids": ranks_ids,
                "rank_display": rank_display,
                "mencao": mencao,
                "data_hora": data_hora,
                "info": info_extra,
                "criada_por": interaction.user.id,
                "criada_por_nome": interaction.user.display_name,
                "criada_em": agora_str_iso(),
                "msg_id": None,
                "canal_id": None,
                "voz_ids": [],
            }
            try:
                msg = await canal.send(
                    content=mencao or None,
                    embed=self._embed_anuncio(p),
                    view=EntrarView(self),
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
            except discord.HTTPException as e:
                self.estado["contador"] -= 1
                await interaction.followup.send(f"❌ Não consegui postar no canal de amistosos: {e}", ephemeral=True)
                return
            p["msg_id"] = msg.id
            self.estado["partidas"][str(pid)] = p
            self._salvar()
        await interaction.followup.send(f"✅ Interno **#{pid}** ({modo.value}) anunciado em {canal.mention}!", ephemeral=True)
        print(f"[INTERNO] ✅ {interaction.user} anunciou o interno #{pid} ({modo.value})")

    def _achar(self, numero: int) -> Optional[dict]:
        return self.estado["partidas"].get(str(numero))

    @app_commands.command(name="interno-resultado", description="[Staff] Diz quem ganhou um interno em andamento.")
    @app_commands.describe(partida="Número do interno", vencedor="Qual time venceu")
    @app_commands.choices(vencedor=[
        app_commands.Choice(name="🔵 Time 1", value=1),
        app_commands.Choice(name="🟠 Time 2", value=2),
    ])
    async def resultado_cmd(self, interaction: discord.Interaction, partida: int, vencedor: app_commands.Choice[int]):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar(partida)
        if p is None or p["status"] != "andamento":
            await interaction.response.send_message("❌ Interno não encontrado ou não está em andamento.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.finalizar(interaction.guild, p, vencedor.value - 1, interaction.user)
        await interaction.followup.send(f"✅ Interno #{partida} registrado: **Time {vencedor.value}** venceu.", ephemeral=True)

    @app_commands.command(name="interno-cancelar", description="[Staff] Cancela um interno (aberto ou em andamento).")
    @app_commands.describe(partida="Número do interno")
    async def cancelar_cmd(self, interaction: discord.Interaction, partida: int):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar(partida)
        if p is None or p["status"] not in ("aberta", "andamento"):
            await interaction.response.send_message("❌ Interno não encontrado ou já encerrado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.cancelar(interaction.guild, p, interaction.user)
        await interaction.followup.send(f"🚫 Interno #{partida} cancelado.", ephemeral=True)

    @app_commands.command(name="interno-desfazer", description="[Staff] Desfaz um resultado registrado por engano (tira as vitórias/derrotas).")
    @app_commands.describe(partida="Número do interno")
    async def desfazer_cmd(self, interaction: discord.Interaction, partida: int):
        if not await self._exigir_staff(interaction):
            return
        p = self._achar(partida)
        if p is None or p["status"] != "finalizada":
            await interaction.response.send_message("❌ Interno não encontrado ou sem resultado registrado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.desfazer(interaction.guild, p)
        await interaction.followup.send(f"↩️ Resultado do interno #{partida} desfeito. As vitórias/derrotas foram retiradas.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Interno(bot))
