import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
WELCOME_CHANNEL_ID   = int(os.getenv("WELCOME_CHANNEL_ID", 0))
NOVO_JOGADOR_ROLE_ID = 1514788887300538531

# ─────────────────────────────────────────────
#  Cog: Boas-vindas
#  Arquivo: cogs/welcome.py
#  Evento: on_member_join
# ─────────────────────────────────────────────

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
            title="✦ Bem-vindo(a) ao servidor!",
            description=(
                f"Olá, {member.mention}! Fico feliz em te ver aqui.\n\n"
                f"Leia as regras e aproveite sua estadia. ⚔️"
            ),
            color=0xD4A843
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="👤 Usuário",        value=member.name,       inline=True)
        embed.add_field(name="📅 Conta criada em", value=created_at,        inline=True)
        embed.add_field(name="👥 Total de membros", value=f"`{member_count}`", inline=True)

        embed.set_footer(
            text=f"{guild.name}",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )

        # Envia a menção do cargo fora do embed (para notificar) + o embed
        await channel.send(content=mencao_cargo if mencao_cargo else None, embed=embed)
        print(f"[WELCOME] ✅ Boas-vindas enviadas para {member} no canal #{channel.name}.")


# ─────────────────────────────────────────────
#  Setup obrigatório para o bot carregar o cog
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
