import re
import asyncio

import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler, salvar
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Conversar por PV
#  Arquivo: cogs/conversar_pv.py
#
#  Comando /conversar-pv — cria um canal-ponte com um membro: tudo que a
#  staff manda nesse canal vai automaticamente por DM pro membro, e tudo
#  que o membro responde por DM aparece automaticamente no canal — sem
#  ninguém precisar copiar/colar nada na mão.
#
#  Guardado em data/conversas_pv.json:
#    {
#      "canais":  {"<canal_id>": {"membro_id":..., "guild_id":..., "staff_id":..., "aberto": true, "criado_em":...}},
#      "membros": {"<membro_id>": <canal_id>},   # lookup reverso pra achar o canal a partir de uma DM
#    }
# ─────────────────────────────────────────────

CATEGORIA_PV_ID = 0
NOME_CATEGORIA_PV = "📨 Conversas Privadas"


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


def _slug(nome: str) -> str:
    nome = nome.lower().strip()
    nome = re.sub(r"[^a-z0-9\-]+", "-", nome)
    nome = re.sub(r"-+", "-", nome).strip("-")
    return nome or "membro"


class EncerrarConversaView(discord.ui.View):
    """View persistente e genérica — o botão descobre a conversa pelo
    próprio canal onde foi clicado, então uma única instância serve pra
    todos os canais-ponte já criados (e os que forem criados depois)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Encerrar Conversa", style=discord.ButtonStyle.danger, custom_id="pv_encerrar_conversa")
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: "ConversarPV" = interaction.client.get_cog("ConversarPV")
        if cog is None:
            return
        await cog.encerrar_conversa(interaction, interaction.channel.id)


class ConversarPV(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("conversas_pv")
        self.dados.setdefault("canais", {})
        self.dados.setdefault("membros", {})
        self.bot.add_view(EncerrarConversaView())

    def _salvar(self):
        salvar("conversas_pv", self.dados)

    async def get_categoria(self, guild: discord.Guild) -> discord.CategoryChannel:
        if CATEGORIA_PV_ID:
            cat = guild.get_channel(CATEGORIA_PV_ID)
            if isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name=NOME_CATEGORIA_PV)
        if cat is None:
            cat = await guild.create_category(NOME_CATEGORIA_PV, reason="Categoria de conversas privadas criada automaticamente")
        return cat

    # ── /conversar-pv ────────────────────────────────────────────────────
    @app_commands.command(name="conversar-pv", description="[Staff] Abre um canal-ponte pra conversar por PV com um membro.")
    @app_commands.describe(membro="Membro com quem você quer conversar por PV")
    async def conversar_pv(self, interaction: discord.Interaction, membro: discord.Member):
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode usar este comando.", ephemeral=True
            )
            return

        if membro.bot:
            await interaction.response.send_message("❌ Não dá pra conversar por PV com um bot.", ephemeral=True)
            return

        canal_existente_id = self.dados["membros"].get(str(membro.id))
        if canal_existente_id:
            canal_existente = interaction.guild.get_channel(int(canal_existente_id))
            if canal_existente:
                await interaction.response.send_message(
                    f"⚠️ Já existe uma conversa aberta com **{membro.display_name}** em {canal_existente.mention}.",
                    ephemeral=True,
                )
                return
            # canal antigo sumiu — limpa o registro velho e segue o baile
            self.dados["canais"].pop(str(canal_existente_id), None)
            self.dados["membros"].pop(str(membro.id), None)
            self._salvar()

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        try:
            categoria = await self.get_categoria(guild)

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            for staff_id in STAFF_IDS:
                role = guild.get_role(staff_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            nome_canal = f"pv-{_slug(membro.name)}"[:95]
            canal = await guild.create_text_channel(
                name=nome_canal,
                category=categoria,
                overwrites=overwrites,
                reason=f"Conversa privada com {membro} aberta por {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão pra criar a categoria/canal. Preciso de **Gerenciar Canais** no servidor.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Erro do Discord ao criar o canal: {e}", ephemeral=True)
            return

        self.dados["canais"][str(canal.id)] = {
            "membro_id": membro.id,
            "guild_id": guild.id,
            "staff_id": interaction.user.id,
            "aberto": True,
            "criado_em": discord.utils.utcnow().isoformat(),
        }
        self.dados["membros"][str(membro.id)] = canal.id
        self._salvar()

        embed = discord.Embed(
            title=f"📨 Conversa privada com {membro.display_name}",
            description=(
                f"Tudo que a **staff mandar aqui** vai automaticamente por PV pra {membro.mention}, "
                f"e tudo que **{membro.display_name} responder por PV** aparece aqui automaticamente.\n\n"
                "Quando terminar, clica em **Encerrar Conversa** abaixo. 🔒"
            ),
            color=0xD4A843,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        await canal.send(embed=embed, view=EncerrarConversaView())

        aviso_dm = ""
        try:
            aviso_embed = discord.Embed(
                description=(
                    f"👋 A staff da **{guild.name}** iniciou uma conversa privada com você.\n"
                    "Pode responder **direto aqui na DM** que sua mensagem chega pra equipe automaticamente."
                ),
                color=0xD4A843,
            )
            await membro.send(embed=aviso_embed)
        except discord.Forbidden:
            aviso_dm = (
                "\n⚠️ Não consegui avisar o membro por PV (DMs fechadas) — mas o canal já tá pronto, "
                "é só mandar a mensagem aqui que ela chega assim que ele abrir a DM do bot."
            )

        await interaction.followup.send(f"✅ Canal criado: {canal.mention}{aviso_dm}", ephemeral=True)
        print(f"[CONVERSAR_PV] 📨 {interaction.user} abriu conversa com {membro} em #{canal.name}")

    # ── encerrar conversa (usado pelo botão) ────────────────────────────
    async def encerrar_conversa(self, interaction: discord.Interaction, canal_id: int):
        registro = self.dados["canais"].get(str(canal_id))
        if not registro:
            await interaction.response.send_message("⚠️ Esse canal não é (ou já não é mais) uma conversa privada ativa.", ephemeral=True)
            return

        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message("❌ Apenas **Staff** pode encerrar a conversa.", ephemeral=True)
            return

        membro_id = registro["membro_id"]
        self.dados["canais"].pop(str(canal_id), None)
        if self.dados["membros"].get(str(membro_id)) == canal_id:
            self.dados["membros"].pop(str(membro_id), None)
        self._salvar()

        await interaction.response.send_message("🔒 Conversa encerrada! Fechando o canal em 5 segundos...")

        membro = interaction.guild.get_member(membro_id) if interaction.guild else None
        if membro:
            try:
                await membro.send(embed=discord.Embed(
                    description="🔒 A staff encerrou essa conversa privada. Se precisar de algo, é só chamar de novo!",
                    color=0x99AAB5,
                ))
            except discord.Forbidden:
                pass

        print(f"[CONVERSAR_PV] 🔒 {interaction.user} encerrou a conversa com <@{membro_id}> (canal {canal_id})")

        await asyncio.sleep(5)
        canal = interaction.channel
        try:
            await canal.delete(reason=f"Conversa privada encerrada por {interaction.user}")
        except discord.HTTPException:
            pass

    # ── retransmissão das mensagens ──────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # staff escreveu no canal-ponte → manda por DM pro membro
        if message.guild is not None:
            registro = self.dados["canais"].get(str(message.channel.id))
            if not registro or not registro.get("aberto", True):
                return

            membro = message.guild.get_member(registro["membro_id"])
            if membro is None:
                return

            conteudo = message.content.strip()
            if not conteudo and not message.attachments:
                return

            texto = conteudo
            for anexo in message.attachments:
                texto = f"{texto}\n{anexo.url}" if texto else anexo.url

            try:
                await membro.send(texto)
                await message.add_reaction("✅")
            except discord.Forbidden:
                await message.channel.send(
                    "⚠️ Não consegui entregar essa mensagem — a DM desse membro tá fechada.", delete_after=10
                )
            except discord.HTTPException:
                pass
            return

        # membro respondeu por DM → manda pro canal-ponte
        canal_id = self.dados["membros"].get(str(message.author.id))
        if not canal_id:
            return

        canal = self.bot.get_channel(int(canal_id))
        if canal is None:
            return

        conteudo = message.content.strip()
        if not conteudo and not message.attachments:
            return

        texto = conteudo
        for anexo in message.attachments:
            texto = f"{texto}\n{anexo.url}" if texto else anexo.url

        try:
            await canal.send(texto)
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass

    # ── limpeza automática se o canal for apagado na mão ─────────────────
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        registro = self.dados["canais"].pop(str(channel.id), None)
        if registro is None:
            return
        membro_id = registro["membro_id"]
        if self.dados["membros"].get(str(membro_id)) == channel.id:
            self.dados["membros"].pop(str(membro_id), None)
        self._salvar()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        msg = f"❌ Deu erro nesse comando: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass
        print(f"[CONVERSAR_PV] ❌ Erro: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ConversarPV(bot))
