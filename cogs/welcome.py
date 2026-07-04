import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

from cogs.players import CARGOS

load_dotenv()
WELCOME_CHANNEL_ID   = int(os.getenv("WELCOME_CHANNEL_ID", 0))
NOVO_JOGADOR_ROLE_ID = 1514788887300538531

# ─────────────────────────────────────────────
#  Cog: Boas-vindas
#  Arquivo: cogs/welcome.py
#  Evento: on_member_join
# ─────────────────────────────────────────────

COR_BOAS_VINDAS = 0xFFD700  # dourado vibrante — bem diferente do tom da despedida

RANKS = [c for c in CARGOS if c["secao"] == "rank"]
RANK_IDS = {c["id"] for c in RANKS}


# ── Select menu: escolher o rank já dá o cargo na hora ──────────────────────
class RegistrarRankSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=c["nome"], emoji=c["emoji"], value=str(c["id"]))
            for c in RANKS
        ]
        super().__init__(
            placeholder="Escolha o seu rank atual...",
            options=options,
            custom_id="boasvindas_select_rank",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        membro = interaction.user
        novo_cargo = guild.get_role(int(self.values[0]))

        if novo_cargo is None:
            await interaction.response.send_message("❌ Não encontrei esse cargo no servidor. Chama a staff!", ephemeral=True)
            return

        # Rank é único — tira qualquer outro rank que a pessoa já tenha antes de dar o novo
        cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS and r.id != novo_cargo.id]

        try:
            if cargos_rank_atuais:
                await membro.remove_roles(*cargos_rank_atuais, reason="Trocou de rank pelo menu de boas-vindas")
            if novo_cargo not in membro.roles:
                await membro.add_roles(novo_cargo, reason="Registrou o rank pelo menu de boas-vindas")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não tenho permissão pra te dar esse cargo. Chama a staff!", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Prontinho! Agora você tem o rank **{novo_cargo.name}**.", ephemeral=True)


class RegistrarRankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RegistrarRankSelect())


class BoasVindasView(discord.ui.View):
    """Botões de dicas + o de registrar rank, que abre o menu de seleção."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 Registrar meu Rank", style=discord.ButtonStyle.primary, custom_id="boasvindas_rank")
    async def registrar_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🎮 Escolha o rank que você faz atualmente no Rocket League:",
            view=RegistrarRankView(),
            ephemeral=True,
        )

    @discord.ui.button(label="📜 Como funciona aqui", style=discord.ButtonStyle.secondary, custom_id="boasvindas_como_funciona")
    async def como_funciona(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📜 **Resumo rápido pra você já sair andando:**\n"
            "• Respeito acima de tudo — sem toxicidade.\n"
            "• Registre seu rank pra participar de campeonatos e amistosos.\n"
            "• Fique de olho nos anúncios pra não perder nenhum torneio.\n"
            "Qualquer dúvida, é só chamar a staff!",
            ephemeral=True,
        )

    @discord.ui.button(label="❓ Preciso de ajuda", style=discord.ButtonStyle.success, custom_id="boasvindas_ajuda")
    async def precisa_ajuda(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "❓ **Precisa de uma força?**\n"
            "Abra um ticket no canal de tickets do servidor, ou chame qualquer um da staff. "
            "A gente te responde o mais rápido possível!",
            ephemeral=True,
        )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if channel is None:
            print(f"[WELCOME] ⚠️  Canal {WELCOME_CHANNEL_ID} não encontrado.")
            return

        guild        = member.guild
        member_count = guild.member_count
        created_at   = discord.utils.format_dt(member.created_at, style="D")

        # Menciona o cargo Notificação Novo Jogador
        cargo_novo_jogador = guild.get_role(NOVO_JOGADOR_ROLE_ID)
        mencao_cargo = cargo_novo_jogador.mention if cargo_novo_jogador else ""

        # ── Embed principal ──────────────────────────────
        embed = discord.Embed(
            title="🎉 Chegou gente nova!",
            description=(
                f"Sejam bem-vindos, {member.mention}! 🚀\n\n"
                f"A **{guild.name}** tá mais completa com você aqui. "
                f"Dá uma olhada nos botões abaixo pra já sair andando! ⚔️"
            ),
            color=COR_BOAS_VINDAS,
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)

        embed.add_field(name="👤 Usuário",         value=member.name,         inline=True)
        embed.add_field(name="📅 Conta criada em",  value=created_at,          inline=True)
        embed.add_field(name="🎊 Você é o membro",  value=f"`#{member_count}`", inline=True)

        embed.set_footer(
            text=f"{guild.name} • Boa sorte nas rankeds! 🏆",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )

        # Menciona a pessoa que entrou + o cargo de Novo Jogador (fora do embed, pra notificar)
        conteudo = f"{member.mention} {mencao_cargo}".strip()

        await channel.send(content=conteudo, embed=embed, view=BoasVindasView())
        print(f"[WELCOME] ✅ Boas-vindas enviadas para {member} no canal #{channel.name}.")


# ─────────────────────────────────────────────
#  Setup obrigatório para o bot carregar o cog
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
