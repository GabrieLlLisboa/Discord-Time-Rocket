import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))

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
        created_at   = discord.utils.format_dt(member.created_at, style="D")  # ex: 15 de março de 2021

        # ── Embed principal ──────────────────────────────
        embed = discord.Embed(
            title="✦ Bem-vindo(a) ao servidor!",
            description=(
                f"Olá, {member.mention}! Fico feliz em te ver aqui.\n\n"
                f"Leia as regras e aproveite sua estadia. ⚔️"
            ),
            color=0xD4A843   # dourado Arvenor
        )

        # Thumbnail = avatar do membro
        embed.set_thumbnail(url=member.display_avatar.url)

        # Campos de informação
        embed.add_field(
            name="👤 Usuário",
            value=f"{member.name}",
            inline=True
        )
        embed.add_field(
            name="📅 Conta criada em",
            value=created_at,
            inline=True
        )
        embed.add_field(
            name="👥 Total de membros",
            value=f"`{member_count}`",
            inline=True
        )

        # Rodapé com ícone do servidor
        embed.set_footer(
            text=f"{guild.name}",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty
        )

        await channel.send(embed=embed)
        print(f"[WELCOME] ✅ Boas-vindas enviadas para {member} no canal #{channel.name}.")


# ─────────────────────────────────────────────
#  Setup obrigatório para o bot carregar o cog
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
