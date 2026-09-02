import discord
from discord.ext import commands

from cogs.whitelist import STAFF_ROLE_IDS

# ─────────────────────────────────────────────
#  Cog: Tag de Staff
#  Arquivo: cogs/staff_tag.py
#
#  Sempre que alguém tem QUALQUER cargo de staff (Sub-Dono, Diretor,
#  Gerente, Moderador, Suporte, Dono, Administrador, Coach, Editor de
#  vídeo...), esse cargo abaixo é adicionado junto automaticamente.
#  Se a pessoa perde todos os cargos de staff, a tag é removida também.
# ─────────────────────────────────────────────

CARGO_TAG_STAFF_ID = 1523843469016043600


class StaffTag(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cargos_ids = {r.id for r in after.roles}
        tem_staff = bool(cargos_ids & STAFF_ROLE_IDS)
        tem_tag = CARGO_TAG_STAFF_ID in cargos_ids

        guild = after.guild
        cargo_tag = guild.get_role(CARGO_TAG_STAFF_ID)
        if cargo_tag is None:
            return

        try:
            if tem_staff and not tem_tag:
                await after.add_roles(cargo_tag, reason="Tem cargo de staff — tag automática")
            elif not tem_staff and tem_tag:
                await after.remove_roles(cargo_tag, reason="Perdeu todos os cargos de staff — remove tag automática")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffTag(bot))
