import discord
from discord.ext import commands


CARGOS_GATILHO = {
    1532739361198833874,
    1525540085112770746,
    1523833330175442954,
    1523835045872275566,
    1523835085475020932,
    1523835010795176027,
    1511895253777649704,
}

CARGO_EQUIPE_ID = 1532184563491541164


class CargoEquipeAuto(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _sincronizar(self, guild: discord.Guild):
        cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
        if cargo_equipe is None:
            return

        for membro in guild.members:
            cargos_ids = {r.id for r in membro.roles}
            tem_gatilho = bool(cargos_ids & CARGOS_GATILHO)
            tem_equipe = CARGO_EQUIPE_ID in cargos_ids

            if tem_gatilho and not tem_equipe:
                try:
                    await membro.add_roles(cargo_equipe, reason="Tem cargo de staff — cargo de equipe automático")
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._sincronizar(guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cargos_ids = {r.id for r in after.roles}
        tem_gatilho = bool(cargos_ids & CARGOS_GATILHO)
        tem_equipe = CARGO_EQUIPE_ID in cargos_ids

        if not tem_gatilho or tem_equipe:
            return

        guild = after.guild
        cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
        if cargo_equipe is None:
            return

        try:
            await after.add_roles(cargo_equipe, reason="Tem cargo de staff — cargo de equipe automático")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(CargoEquipeAuto(bot))
