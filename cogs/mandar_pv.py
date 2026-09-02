import discord
from discord.ext import commands
from discord import app_commands

from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Mandar PV
#  Arquivo: cogs/mandar_pv.py
#
#  Comando /mandar-pv — só Staff. Manda uma DM pra um membro do servidor
#  em nome do clube (embed padronizado, avisando quem mandou), útil pra
#  avisos individuais sem precisar sair do Discord/abrir DM na mão.
# ─────────────────────────────────────────────


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


class MandarPV(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mandar-pv", description="[Staff] Manda uma mensagem privada (DM) pra um membro.")
    @app_commands.describe(
        membro="Membro que vai receber a mensagem",
        mensagem="Texto da mensagem a enviar",
    )
    async def mandar_pv(self, interaction: discord.Interaction, membro: discord.Member, mensagem: str):
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode usar este comando.", ephemeral=True
            )
            return

        if membro.bot:
            await interaction.response.send_message("❌ Não dá pra mandar PV pra um bot.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="📩 Mensagem da TryHarders RL",
            description=mensagem.strip()[:4000],
            color=0xD4A843,
        )
        embed.set_footer(
            text=f"Enviado por {interaction.user.display_name} • {interaction.guild.name}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.timestamp = discord.utils.utcnow()

        try:
            await membro.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Não consegui mandar PV pra **{membro.display_name}** — ele(a) deve estar com DMs fechadas.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Erro ao enviar a mensagem: {e}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Mensagem enviada por PV pra **{membro.display_name}**!", ephemeral=True
        )
        print(f"[MANDAR_PV] 📩 {interaction.user} mandou PV pra {membro}: {mensagem[:80]!r}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MandarPV(bot))
