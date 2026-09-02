import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler, salvar
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Anúncios
#  Arquivo: cogs/anunciar.py
#
#  A Staff escreve um anúncio através de um Modal e o bot publica
#  automaticamente no canal configurado (data/anuncios_config.json,
#  guardado por servidor: {"<guild_id>": {"canal_id": ...}}), sempre com o
#  mesmo formato de embed — sem precisar a Staff montar embed na mão.
#
#  Cargo de notificação opcional: reaproveita o cargo "Notificação Anúncios"
#  já usado em cogs/notifications.py, se quiser marcar todo mundo que
#  ativou aquele cargo.
# ─────────────────────────────────────────────

CARGO_NOTIFICACAO_ANUNCIOS_ID = 1514788861090205839


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


def _get_canal_id(guild_id: int) -> int | None:
    config = ler("anuncios_config")
    return config.get(str(guild_id), {}).get("canal_id")


class AnuncioModal(discord.ui.Modal, title="📢 Novo Anúncio"):
    titulo_anuncio = discord.ui.TextInput(
        label="Título do anúncio",
        placeholder="Ex: Novo horário de treinos",
        max_length=200,
    )
    mensagem = discord.ui.TextInput(
        label="Mensagem",
        style=discord.TextStyle.paragraph,
        placeholder="Escreva o conteúdo do anúncio aqui...",
        max_length=3500,
    )
    imagem_url = discord.ui.TextInput(
        label="URL de imagem (opcional)",
        required=False,
        placeholder="https://...",
    )
    mencionar = discord.ui.TextInput(
        label="Marcar cargo de notificação? (sim/não)",
        required=False,
        placeholder="sim ou não",
        max_length=10,
    )

    def __init__(self, cog: "Anunciar"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.publicar_anuncio(
            interaction,
            self.titulo_anuncio.value,
            self.mensagem.value,
            self.imagem_url.value,
            self.mencionar.value,
        )


class Anunciar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def publicar_anuncio(
        self,
        interaction: discord.Interaction,
        titulo: str,
        mensagem: str,
        imagem_url: str,
        mencionar_raw: str,
    ):
        canal_id = _get_canal_id(interaction.guild_id)
        if canal_id is None:
            await interaction.response.send_message(
                "❌ Nenhum canal de anúncios configurado ainda. "
                "Peça pra um Administrador rodar `/anunciar-canal` primeiro.",
                ephemeral=True,
            )
            return

        canal = interaction.guild.get_channel(canal_id)
        if canal is None:
            await interaction.response.send_message(
                "❌ O canal configurado pra anúncios não existe mais. Rode `/anunciar-canal` de novo.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📢 {titulo.strip()}",
            description=mensagem.strip(),
            color=0xD4A843,
        )
        if imagem_url.strip():
            embed.set_image(url=imagem_url.strip())
        embed.set_footer(text=f"TryHarders RL 🚀 • Anunciado por {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()

        conteudo = None
        aviso_extra = ""
        allowed = discord.AllowedMentions.none()
        if mencionar_raw.strip().lower() in ("sim", "s", "yes", "y"):
            cargo = canal.guild.get_role(CARGO_NOTIFICACAO_ANUNCIOS_ID)
            if cargo:
                conteudo = cargo.mention
                allowed = discord.AllowedMentions(roles=True)
            else:
                aviso_extra = "\n⚠️ Cargo de notificação de anúncios não encontrado — publicado sem marcação."

        try:
            await canal.send(content=conteudo, embed=embed, allowed_mentions=allowed)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Não tenho permissão pra enviar mensagens em {canal.mention}.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Anúncio publicado em {canal.mention}!{aviso_extra}", ephemeral=True
        )
        print(f"[ANUNCIAR] 📢 {interaction.user} publicou anúncio '{titulo}' em #{canal.name}")

    # ── /anunciar — abre o modal (só Staff) ──────────────────────────────
    @app_commands.command(name="anunciar", description="[Staff] Escreve e publica um anúncio no canal configurado.")
    async def anunciar_cmd(self, interaction: discord.Interaction):
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode publicar anúncios.", ephemeral=True
            )
            return
        await interaction.response.send_modal(AnuncioModal(self))

    # ── /anunciar-canal — configura o canal (só Administrador) ──────────
    @app_commands.command(name="anunciar-canal", description="[Admin] Define o canal onde os anúncios serão publicados.")
    @app_commands.describe(canal="Canal onde o /anunciar vai publicar")
    @app_commands.checks.has_permissions(administrator=True)
    async def anunciar_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        config = ler("anuncios_config")
        config[str(interaction.guild_id)] = {"canal_id": canal.id}
        salvar("anuncios_config", config)

        await interaction.response.send_message(
            f"✅ Canal de anúncios definido: {canal.mention}", ephemeral=True
        )
        print(f"[ANUNCIAR] ⚙️ {interaction.user} definiu o canal de anúncios: #{canal.name}")

    @anunciar_canal.error
    async def anunciar_canal_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem configurar o canal de anúncios.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Anunciar(bot))
