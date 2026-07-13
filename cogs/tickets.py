import discord
from discord.ext import commands
import time

# ─────────────────────────────────────────────
#  Cog: Tíquetes
#  Arquivo: cogs/tickets.py
#  Comandos: !setup
#  Abre canal privado por categoria
# ─────────────────────────────────────────────

# ── Anti-abuso na criação de tickets ────────────────────────────────────────
# ANTES: não havia cooldown nem limite de tickets simultâneos — qualquer
# usuário podia clicar repetidamente no menu e abrir vários canais em
# sequência (flood de canais, aproximação do limite de canais do servidor,
# rate limit da API do Discord, possível ataque com contas alternativas).
#
# AGORA:
#  - COOLDOWN_SEGUNDOS: tempo mínimo entre duas criações de ticket pelo
#    mesmo usuário. Uma segunda tentativa dentro da janela é rejeitada sem
#    criar canal nenhum (sem erro, só um aviso ephemeral).
#  - MAX_TICKETS_SIMULTANEOS: quantidade máxima de tickets que um mesmo
#    usuário pode manter abertos ao mesmo tempo (somando todas as
#    categorias). Ao atingir o limite, novas criações são bloqueadas até
#    que algum ticket existente seja fechado.
# Os dados ficam em memória (nível de módulo, não por instância de View),
# então valem para qualquer instância da view — inclusive a persistente
# registrada em main.py — enquanto o processo do bot estiver rodando.
COOLDOWN_SEGUNDOS       = 60
MAX_TICKETS_SIMULTANEOS = 3
_ultima_criacao: dict[int, float] = {}  # user_id -> timestamp (time.monotonic())

CATEGORIAS = [
    discord.SelectOption(
        label="Dúvidas",
        description="Tem alguma dúvida? Fale com a equipe.",
        emoji="❓",
        value="duvidas"
    ),
    discord.SelectOption(
        label="Denúncias",
        description="Reporte um jogador ou situação.",
        emoji="🚨",
        value="denuncias"
    ),
    discord.SelectOption(
        label="Mais sobre o time",
        description="Quer saber mais sobre nossa equipe?",
        emoji="🏆",
        value="time"
    ),
    discord.SelectOption(
        label="Problemas Técnicos",
        description="Encontrou algum bug ou erro?",
        emoji="🔧",
        value="tecnico"
    ),
]

NOMES = {
    "duvidas":   "duvida",
    "denuncias": "denuncia",
    "time":      "time",
    "tecnico":   "tecnico",
}

CORES = {
    "duvidas":   0x5865F2,
    "denuncias": 0xED4245,
    "time":      0xFEE75C,
    "tecnico":   0x57F287,
}


# ── Select Menu ────────────────────────────────────────────────────────────────
class TicketSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            custom_id="ticket_select",
            placeholder="📂 Selecione o tipo de suporte...",
            min_values=1,
            max_values=1,
            options=CATEGORIAS,
        )

    async def callback(self, interaction: discord.Interaction):
        valor     = self.values[0]
        guild     = interaction.guild
        membro    = interaction.user

        # ── Cooldown por usuário ────────────────────────────────────────
        agora  = time.monotonic()
        ultima = _ultima_criacao.get(membro.id)
        if ultima is not None and (agora - ultima) < COOLDOWN_SEGUNDOS:
            restante = int(COOLDOWN_SEGUNDOS - (agora - ultima)) + 1
            await interaction.response.send_message(
                f"⏳ Aguarde `{restante}s` antes de abrir outro tíquete.",
                ephemeral=True
            )
            return

        # Nome do canal baseado no ID do usuário — não no username.
        # ANTES: usava membro.name, então dois usernames parecidos podiam
        # colidir, um usuário podia mudar de nome e "perder" a associação
        # com o próprio ticket, e dava pra descobrir se outra pessoa tinha
        # ticket aberto só testando nomes parecidos. O ID do Discord é
        # único, estável e não muda com o usuário renomeando a conta.
        nome_canal = f"ticket-{NOMES[valor]}-{membro.id}"

        # Verifica se já tem tíquete aberto dessa categoria
        existente = discord.utils.get(guild.text_channels, name=nome_canal)
        if existente:
            await interaction.response.send_message(
                f"⚠️ Você já tem um tíquete aberto: {existente.mention}",
                ephemeral=True
            )
            return

        # ── Limite de tickets simultâneos (todas as categorias) ──────────
        abertos = [
            c for c in guild.text_channels
            if c.name.startswith("ticket-") and c.name.endswith(f"-{membro.id}")
        ]
        if len(abertos) >= MAX_TICKETS_SIMULTANEOS:
            await interaction.response.send_message(
                f"⚠️ Você já possui `{len(abertos)}` tíquete(s) aberto(s) "
                f"(limite: `{MAX_TICKETS_SIMULTANEOS}`). Feche algum antes de abrir outro.",
                ephemeral=True
            )
            return

        # Marca a tentativa já aqui (antes de criar o canal) para fechar a
        # janela de corrida: dois cliques rápidos em sequência não devem
        # conseguir passar pelo cooldown os dois.
        _ultima_criacao[membro.id] = agora

        # Permissões do canal
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro:             discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        # Administradores também veem
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Cria o canal
        canal = await guild.create_text_channel(
            name=nome_canal,
            overwrites=overwrites,
            reason=f"Tíquete aberto por {membro} — {valor}"
        )

        # Embed de abertura dentro do tíquete
        embed = discord.Embed(
            title=f"Tíquete — {self.options[[o.value for o in self.options].index(valor)].label}",
            description=(
                f"Olá, {membro.mention}! 👋\n\n"
                f"A equipe irá te atender em breve.\n"
                f"Descreva seu problema ou dúvida abaixo."
            ),
            color=CORES[valor]
        )
        embed.set_footer(text="Para fechar este tíquete, um administrador pode deletar o canal.")
        embed.set_thumbnail(url=membro.display_avatar.url)

        # Botão de fechar
        view = FecharTicketView()
        await canal.send(content=membro.mention, embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Tíquete aberto! Acesse: {canal.mention}",
            ephemeral=True
        )
        print(f"[TICKET] ✅ Canal {nome_canal} criado para {membro}.")


# ── Botão de fechar tíquete ────────────────────────────────────────────────────
class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fechar Tíquete", style=discord.ButtonStyle.danger, custom_id="fechar_ticket")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Apenas administradores podem fechar
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem fechar tíquetes.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("🔒 Fechando tíquete em 3 segundos...")
        import asyncio
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Tíquete fechado por {interaction.user}")


# ── View do setup (Select Menu) ────────────────────────────────────────────────
class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ── Cog principal ──────────────────────────────────────────────────────────────
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context):
        """Envia o painel de abertura de tíquetes no canal atual."""
        await ctx.message.delete()

        embed = discord.Embed(
            title="🎫 Central de Suporte",
            description=(
                "Precisa de ajuda? Selecione uma categoria abaixo\n"
                "e um canal privado será criado para você.\n\n"
                "❓ **Dúvidas** — Perguntas gerais\n"
                "🚨 **Denúncias** — Reporte jogadores\n"
                "🏆 **Mais sobre o time** — Conheça a equipe\n"
                "🔧 **Problemas Técnicos** — Bugs e erros"
            ),
            color=0x2B2D31
        )
        embed.set_footer(text="Apenas você e a equipe verão seu tíquete.")

        await ctx.send(embed=embed, view=TicketSetupView())
        print(f"[TICKET] ✅ Painel de tíquetes enviado em #{ctx.channel.name} por {ctx.author}.")

    @setup.error
    async def setup_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa ser **Administrador** para usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
