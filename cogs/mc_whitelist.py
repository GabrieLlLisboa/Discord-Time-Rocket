"""Whitelist do servidor de Minecraft.

Fluxo:
  1. Alguém entra no servidor -> o bot cria um canal privado só dele.
  2. Ele clica em "Começar" e responde:
        • Qual seu nick do Minecraft?   (o apelido no Discord vira esse nick)
        • Java ou Bedrock?
  3. A staff recebe o resumo e aprova ou recusa.
        • Aprovou: tira o cargo "sem acesso", dá o cargo de membro, canal some em 10 min.
        • Recusou: expulsa a pessoa, canal some em 10 min.
"""
import asyncio
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import discord
from discord.ext import commands, tasks

from cogs import mc_config as cfg


NOME_CATEGORIA = "🔒 Whitelist"
APAGAR_CANAL_APOS_SEGUNDOS = 10 * 60
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mc_whitelist.json"

EDICOES = {"Java": "☕", "Bedrock": "🪨"}

# Java: 3 a 16 caracteres, só letras, números e _
NICK_JAVA = re.compile(r"^[A-Za-z0-9_]{3,16}$")
# Bedrock: gamertag (letras, números, espaço); aceita também "." no começo (Geyser)
NICK_BEDROCK = re.compile(r"^[A-Za-z0-9_. ]{1,16}$")

STATUS_ABERTOS = ("em_andamento", "pendente")


# ───────────────────────── helpers ─────────────────────────

def _slug(nome: str) -> str:
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^a-z0-9\-]+", "-", nome.lower().strip())
    return re.sub(r"-+", "-", nome).strip("-") or "jogador"


def eh_staff(membro: discord.abc.User) -> bool:
    perms = getattr(membro, "guild_permissions", None)
    if perms is not None and perms.administrator:
        return True
    staff_ids = cfg.staff_role_ids()
    return any(r.id in staff_ids for r in getattr(membro, "roles", []))


def _cog(interaction: discord.Interaction) -> "McWhitelist":
    return interaction.client.get_cog("McWhitelist")


async def _responder(interaction: discord.Interaction, texto: str, **kw) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(texto, **kw)
        else:
            await interaction.response.send_message(texto, **kw)
    except discord.HTTPException:
        pass


def _log_erro(onde: str, error: BaseException) -> None:
    import traceback
    print(f"[WHITELIST] ❌ Erro em {onde}: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


MSG_ERRO = "⚠️ Algo deu errado. Tenta de novo ou chama alguém da staff."


# ───────────────────────── views / modal ─────────────────────────

class NickModal(discord.ui.Modal, title="Whitelist — Minecraft"):
    nick = discord.ui.TextInput(
        label="Qual seu nick do Minecraft?",
        placeholder="Ex: Steve",
        min_length=1,
        max_length=16,
        required=True,
    )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        _log_erro("NickModal", error)
        await _responder(interaction, MSG_ERRO, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        cog = _cog(interaction)
        registro = await cog.checar_dono(interaction)
        if registro is None:
            return

        nick = " ".join(self.nick.value.split())
        if not NICK_BEDROCK.match(nick):
            await interaction.response.send_message(
                "⚠️ Nick inválido. Use só letras, números e `_` (até 16 caracteres).", ephemeral=True
            )
            return

        await interaction.response.defer()
        membro = interaction.user
        async with cog.trava(membro.id):
            registro["nick"] = nick
            primeira_vez = not registro.get("edicao_enviada")
            registro["edicao_enviada"] = True
            cog.salvar()

        # o apelido no Discord vira o nick do Minecraft
        aviso = ""
        try:
            await membro.edit(nick=nick, reason="Whitelist — nick do Minecraft")
        except discord.HTTPException:
            aviso = "\n⚠️ Não consegui mudar seu apelido (permissão), mas seguimos!"

        await interaction.followup.send(f"✅ Nick registrado: **{nick}**{aviso}")

        if primeira_vez:
            embed = discord.Embed(
                title="🎮 Java ou Bedrock?",
                description="Escolha a edição do Minecraft que você joga:",
                color=0x5865F2,
            )
            await interaction.channel.send(embed=embed, view=EdicaoView())


class ComecarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Começar", emoji="🚀", style=discord.ButtonStyle.success, custom_id="mcwl:comecar")
    async def comecar(self, interaction: discord.Interaction, button: discord.ui.Button):
        registro = await _cog(interaction).checar_dono(interaction)
        if registro is None:
            return
        if registro.get("edicao_enviada"):
            await interaction.response.send_message(
                "Você já informou seu nick — responda a pergunta de edição abaixo.", ephemeral=True
            )
            return
        await interaction.response.send_modal(NickModal())


class EdicaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        custom_id="mcwl:edicao",
        placeholder="Selecione a edição...",
        options=[discord.SelectOption(label=nome, emoji=emoji, value=nome) for nome, emoji in EDICOES.items()],
    )
    async def escolher(self, interaction: discord.Interaction, select: discord.ui.Select):
        cog = _cog(interaction)
        registro = await cog.checar_dono(interaction)
        if registro is None:
            return

        edicao = select.values[0]
        nick = registro.get("nick", "")
        regra = NICK_JAVA if edicao == "Java" else NICK_BEDROCK
        if not regra.match(nick):
            await interaction.response.send_message(
                f"⚠️ O nick **{nick}** não é válido no Minecraft Java (3 a 16 caracteres, só letras, "
                "números e `_`). Clique em **✏️ Corrigir nick** e escolha de novo.",
                ephemeral=True,
            )
            return

        await cog.enviar_para_aprovacao(interaction, registro, edicao)

    @discord.ui.button(label="Corrigir nick", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="mcwl:renick")
    async def corrigir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await _cog(interaction).checar_dono(interaction) is None:
            return
        await interaction.response.send_modal(NickModal())


class RevisaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success, custom_id="mcwl:aprovar")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = _cog(interaction)
        membro_id = await cog.checar_staff(interaction)
        if membro_id is None:
            return
        await interaction.response.defer(ephemeral=True)
        _, texto = await cog.decidir(interaction.guild, membro_id, interaction.user, aprovar=True)
        await interaction.followup.send(texto, ephemeral=True)

    @discord.ui.button(label="Recusar", emoji="❌", style=discord.ButtonStyle.danger, custom_id="mcwl:recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = _cog(interaction)
        membro_id = await cog.checar_staff(interaction)
        if membro_id is None:
            return
        await interaction.response.send_message(
            "⚠️ Recusar **expulsa** a pessoa do servidor. Confirma?",
            view=ConfirmarRecusaView(membro_id, interaction.user.id),
            ephemeral=True,
        )


class ConfirmarRecusaView(discord.ui.View):
    def __init__(self, membro_id: int, autor_id: int):
        super().__init__(timeout=60)
        self.membro_id = membro_id
        self.autor_id = autor_id

    @discord.ui.button(label="Confirmar recusa", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Esse botão não é seu.", ephemeral=True)
            return
        await interaction.response.edit_message(content="⏳ Processando...", view=None)
        _, texto = await _cog(interaction).decidir(interaction.guild, self.membro_id, interaction.user, aprovar=False)
        await interaction.edit_original_response(content=texto)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Ok, nada foi feito.", view=None)


# ───────────────────────── cog ─────────────────────────

class McWhitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados: dict[str, dict] = self._carregar()
        self._travas: dict[int, asyncio.Lock] = {}

    # ---- persistência ----

    @staticmethod
    def _carregar() -> dict:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def salvar(self) -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

    def trava(self, membro_id: int) -> asyncio.Lock:
        return self._travas.setdefault(membro_id, asyncio.Lock())

    # ---- ciclo de vida ----

    async def cog_load(self):
        # views persistentes: os botões continuam funcionando depois de reiniciar o bot
        self.bot.add_view(ComecarView())
        self.bot.add_view(EdicaoView())
        self.bot.add_view(RevisaoView())
        self.limpeza_canais.start()

    def cog_unload(self):
        self.limpeza_canais.cancel()

    @tasks.loop(minutes=1)
    async def limpeza_canais(self):
        agora = time.time()
        mudou = False
        for registro in self.dados.values():
            deletar_em = registro.get("deletar_em")
            if not deletar_em or registro.get("canal_apagado") or deletar_em > agora:
                continue
            canal = self.bot.get_channel(registro.get("canal_id") or 0)
            if canal is not None:
                try:
                    await canal.delete(reason="Whitelist finalizada")
                except discord.HTTPException:
                    continue
            registro["canal_apagado"] = True
            mudou = True
        if mudou:
            self.salvar()

    @limpeza_canais.before_loop
    async def _antes_limpeza(self):
        await self.bot.wait_until_ready()

    # ---- buscas / checagens ----

    def membro_id_do_canal(self, canal_id: int) -> int | None:
        for membro_id, registro in self.dados.items():
            if registro.get("canal_id") == canal_id:
                return int(membro_id)
        return None

    def membro_id_da_interacao(self, interaction: discord.Interaction) -> int | None:
        """Descobre de quem é a whitelist: pelo canal dela ou, se o clique veio do
        canal de log da staff, pela mensagem de revisão."""
        achado = self.membro_id_do_canal(interaction.channel_id or 0)
        if achado is not None:
            return achado
        msg_id = interaction.message.id if interaction.message else 0
        for membro_id, registro in self.dados.items():
            if any(m.get("msg_id") == msg_id for m in registro.get("revisao_msgs", [])):
                return int(membro_id)
        return None

    async def checar_dono(self, interaction: discord.Interaction) -> dict | None:
        """Só quem está fazendo a whitelist (e só enquanto ela está em andamento)."""
        membro_id = self.membro_id_do_canal(interaction.channel_id or 0)
        registro = self.dados.get(str(membro_id)) if membro_id else None
        if registro is None:
            await _responder(interaction, "⚠️ Essa whitelist não existe mais.", ephemeral=True)
            return None
        if interaction.user.id != membro_id:
            await _responder(interaction, "⚠️ Só quem está fazendo a whitelist pode responder.", ephemeral=True)
            return None
        if registro.get("status") != "em_andamento":
            await _responder(interaction, "⚠️ Não dá mais pra mexer nessa whitelist.", ephemeral=True)
            return None
        return registro

    async def checar_staff(self, interaction: discord.Interaction) -> int | None:
        if not eh_staff(interaction.user):
            await _responder(interaction, "⛔ Só a staff pode decidir whitelists.", ephemeral=True)
            return None
        membro_id = self.membro_id_da_interacao(interaction)
        if membro_id is None:
            await _responder(interaction, "⚠️ Não achei essa whitelist.", ephemeral=True)
            return None
        return membro_id

    # ---- entrada / saída de membros ----

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or member.guild.id != cfg.guild_id():
            return
        try:
            await self.criar_canal(member)
        except Exception as e:
            _log_erro(f"criar_canal({member})", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != cfg.guild_id():
            return
        registro = self.dados.get(str(member.id))
        if not registro or registro.get("status") not in STATUS_ABERTOS:
            return
        registro["status"] = "cancelada"
        registro["deletar_em"] = time.time() + 60
        registro["canal_apagado"] = False
        self.salvar()
        await self._fechar_revisao(member.guild, registro, "🚫 Saiu do servidor", 0x99AAB5)

    async def _get_categoria(self, guild: discord.Guild) -> discord.CategoryChannel:
        if cfg.category_id():
            cat = guild.get_channel(cfg.category_id())
            if isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name=NOME_CATEGORIA)
        if cat is None:
            cat = await guild.create_category(
                NOME_CATEGORIA,
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                reason="Categoria das whitelists",
            )
        return cat

    async def criar_canal(self, member: discord.Member) -> discord.TextChannel:
        guild = member.guild

        sem_acesso = guild.get_role(cfg.no_access_role_id()) if cfg.no_access_role_id() else None
        if sem_acesso and sem_acesso not in member.roles:
            try:
                await member.add_roles(sem_acesso, reason="Entrou — aguardando whitelist")
            except discord.HTTPException:
                pass

        antigo = self.dados.get(str(member.id))
        if antigo:
            canal_antigo = guild.get_channel(antigo.get("canal_id") or 0)
            if antigo.get("status") in STATUS_ABERTOS and canal_antigo is not None:
                return canal_antigo  # já tem uma em aberto: reaproveita
            if canal_antigo is not None:
                try:
                    await canal_antigo.delete(reason="Nova whitelist do mesmo membro")
                except discord.HTTPException:
                    pass

        nome_canal = f"whitelist-{_slug(member.name)}"
        if discord.utils.get(guild.text_channels, name=nome_canal):
            nome_canal += f"-{str(member.id)[-4:]}"

        visivel = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: visivel,
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in cfg.staff_role_ids():
            staff_role = guild.get_role(role_id)
            if staff_role:
                overwrites[staff_role] = visivel

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=await self._get_categoria(guild),
            overwrites=overwrites,
            reason=f"Whitelist de {member}",
        )

        self.dados[str(member.id)] = {
            "status": "em_andamento",
            "canal_id": canal.id,
            "criado_ts": time.time(),
        }
        self.salvar()

        embed = discord.Embed(
            title="⛏️ Bem-vindo(a)! Vamos fazer sua Whitelist",
            description=(
                f"Olá, {member.mention}! Antes de liberar o servidor pra você, "
                "precisamos de **2 informações rápidas**:\n\n"
                "• Seu **nick do Minecraft**\n"
                "• Se você joga no **Java** ou no **Bedrock**\n\n"
                "Clica no botão abaixo pra começar 👇"
            ),
            color=0x57F287,
        )
        embed.set_footer(text="Leva menos de 1 minuto!")
        await canal.send(content=member.mention, embed=embed, view=ComecarView())
        return canal

    # ---- envio pra staff ----

    @staticmethod
    def _embed_resumo(membro: discord.abc.User, registro: dict, titulo: str, cor: int) -> discord.Embed:
        nick = registro.get("nick", "—")
        edicao = registro.get("edicao", "—")
        embed = discord.Embed(title=titulo, color=cor)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="Discord", value=f"{membro.mention} (`{membro}`)", inline=False)
        embed.add_field(name="Nick do Minecraft", value=f"`{nick}`", inline=True)
        embed.add_field(name="Edição", value=f"{EDICOES.get(edicao, '')} {edicao}", inline=True)
        if edicao == "Java":
            embed.add_field(name="Perfil", value=f"[NameMC](https://namemc.com/profile/{nick})", inline=True)
        embed.set_footer(text=f"ID: {membro.id}")
        return embed

    async def enviar_para_aprovacao(self, interaction: discord.Interaction, registro: dict, edicao: str):
        membro = interaction.user
        guild = interaction.guild
        canal = interaction.channel

        async with self.trava(membro.id):
            if registro.get("status") != "em_andamento":  # clique duplo
                await _responder(interaction, "⚠️ Já enviei sua whitelist pra staff.", ephemeral=True)
                return
            registro["edicao"] = edicao
            registro["status"] = "pendente"
            registro["enviado_ts"] = time.time()
            self.salvar()

        # tira o menu da mensagem (evita responder 2x) e avisa o candidato
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(
            f"📨 **Whitelist enviada!** Edição: **{edicao}**. Alguém da staff vai revisar e te avisar por aqui. ⏳"
        )
        try:
            await canal.set_permissions(membro, view_channel=True, send_messages=False, read_message_history=True)
        except discord.HTTPException:
            pass

        titulo = f"📋 Whitelist aguardando revisão — {membro.display_name}"
        revisao_msgs = []

        ping = f"<@&{cfg.ping_role_id()}>" if cfg.ping_role_id() else None
        msg = await canal.send(
            content=ping,
            embed=self._embed_resumo(membro, registro, titulo, 0xFEE75C),
            view=RevisaoView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        revisao_msgs.append({"canal_id": canal.id, "msg_id": msg.id})

        if cfg.log_channel_id():
            canal_log = self.bot.get_channel(cfg.log_channel_id())
            if canal_log:
                try:
                    embed_log = self._embed_resumo(membro, registro, titulo, 0xFEE75C)
                    embed_log.add_field(name="Chat", value=canal.mention, inline=False)
                    msg_log = await canal_log.send(embed=embed_log, view=RevisaoView())
                    revisao_msgs.append({"canal_id": canal_log.id, "msg_id": msg_log.id})
                except discord.HTTPException as e:
                    print(f"[WHITELIST] ⚠️ Não consegui enviar pro canal de log: {e}")

        registro["revisao_msgs"] = revisao_msgs
        self.salvar()

    async def _fechar_revisao(self, guild: discord.Guild, registro: dict, texto: str, cor: int):
        """Tira os botões das mensagens de revisão e marca o resultado nelas."""
        for ref in registro.get("revisao_msgs", []):
            canal = guild.get_channel(ref.get("canal_id") or 0)
            if canal is None:
                continue
            try:
                msg = await canal.fetch_message(ref["msg_id"])
                embed = msg.embeds[0] if msg.embeds else discord.Embed()
                embed.color = cor
                embed.add_field(name="Resultado", value=texto, inline=False)
                await msg.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass

    # ---- decisão ----

    async def decidir(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, aprovar: bool) -> tuple[bool, str]:
        async with self.trava(membro_id):
            registro = self.dados.get(str(membro_id))
            if registro is None:
                return False, "⚠️ Whitelist não encontrada."
            status = registro.get("status")
            if status == "em_andamento":
                return False, "⚠️ Essa pessoa ainda não terminou de responder."
            if status != "pendente":
                return False, f"⚠️ Essa whitelist já está **{status}**."

            membro = guild.get_member(membro_id)
            canal = guild.get_channel(registro.get("canal_id") or 0)
            if membro is None:
                return False, "⚠️ O membro não está mais no servidor."

            registro["status"] = "aprovada" if aprovar else "recusada"
            registro["decidido_por"] = str(autor)
            registro["decidido_por_id"] = autor.id
            registro["decidido_em"] = time.time()
            registro["deletar_em"] = time.time() + APAGAR_CANAL_APOS_SEGUNDOS
            registro["canal_apagado"] = False
            self.salvar()

            if aprovar:
                return True, await self._aprovar(guild, membro, canal, registro, autor)
            return True, await self._recusar(guild, membro, canal, registro, autor)

    async def _aprovar(self, guild, membro: discord.Member, canal, registro: dict, autor) -> str:
        avisos = []

        sem_acesso = guild.get_role(cfg.no_access_role_id()) if cfg.no_access_role_id() else None
        if sem_acesso and sem_acesso in membro.roles:
            try:
                await membro.remove_roles(sem_acesso, reason=f"Whitelist aprovada por {autor}")
            except discord.HTTPException:
                avisos.append("⚠️ Não consegui remover o cargo de \"sem acesso\".")

        cargo_membro = guild.get_role(cfg.member_role_id()) if cfg.member_role_id() else None
        if cargo_membro:
            try:
                await membro.add_roles(cargo_membro, reason=f"Whitelist aprovada por {autor}")
            except discord.HTTPException:
                avisos.append("⚠️ Não consegui dar o cargo de membro (confira a hierarquia de cargos).")

        nick = registro.get("nick")
        if nick and membro.nick != nick:
            try:
                await membro.edit(nick=nick, reason="Whitelist aprovada — nick do Minecraft")
            except discord.HTTPException:
                avisos.append("⚠️ Não consegui ajustar o apelido.")

        if canal is not None:
            try:
                await canal.set_permissions(membro, overwrite=None)
            except discord.HTTPException:
                pass
            await canal.send(
                f"✅ **Whitelist aprovada por {autor.mention}!** {membro.mention} bem-vindo(a) ao servidor! ⛏️\n"
                "*(este canal vai ser apagado em 10 minutos)*",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        await self._fechar_revisao(guild, registro, f"✅ Aprovada por {autor}", 0x57F287)
        return "✅ Whitelist aprovada." + ("\n" + "\n".join(avisos) if avisos else "")

    async def _recusar(self, guild, membro: discord.Member, canal, registro: dict, autor) -> str:
        if canal is not None:
            await canal.send(
                f"❌ **Whitelist recusada por {autor.mention}.** {membro.mention} foi removido do servidor.\n"
                "*(este canal vai ser apagado em 10 minutos)*",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        aviso = ""
        try:
            await membro.kick(reason=f"Whitelist recusada por {autor}")
        except discord.HTTPException:
            aviso = "\n⚠️ Não consegui expulsar (falta permissão ou hierarquia de cargo) — remova manualmente."
        await self._fechar_revisao(guild, registro, f"❌ Recusada por {autor}", 0xED4245)
        return "❌ Whitelist recusada." + aviso

    # ---- comandos da staff (prefixo) ----

    @commands.command(name="mcwhitelist")
    @commands.guild_only()
    @commands.check(lambda ctx: eh_staff(ctx.author))
    async def mc_whitelist_manual(self, ctx: commands.Context, membro: discord.Member):
        """!mcwhitelist @membro — abre (ou reabre) a whitelist de Minecraft de alguém."""
        canal = await self.criar_canal(membro)
        await ctx.send(f"✅ Whitelist de {membro.mention} aberta em {canal.mention}.", delete_after=10)

    async def _comando_decisao(self, ctx: commands.Context, aprovar: bool):
        membro_id = self.membro_id_do_canal(ctx.channel.id)
        if membro_id is None:
            await ctx.send("⚠️ Use esse comando dentro do canal da whitelist.", delete_after=10)
            return
        _, texto = await self.decidir(ctx.guild, membro_id, ctx.author, aprovar)
        await ctx.send(texto, delete_after=15)

    @commands.command(name="mcaprovar")
    @commands.guild_only()
    @commands.check(lambda ctx: eh_staff(ctx.author))
    async def mc_aprovar_cmd(self, ctx: commands.Context):
        await self._comando_decisao(ctx, True)

    @commands.command(name="mcrecusar")
    @commands.guild_only()
    @commands.check(lambda ctx: eh_staff(ctx.author))
    async def mc_recusar_cmd(self, ctx: commands.Context):
        await self._comando_decisao(ctx, False)


async def setup(bot: commands.Bot):
    await bot.add_cog(McWhitelist(bot))
