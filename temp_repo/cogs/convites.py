import discord
from discord.ext import commands

from cogs.json_store import ler_json, salvar_json


CANAL_CONVITES_ID = 1523750525210984661

DATA_PATH = "data/convites.json"


def _ler() -> dict:
    return ler_json(DATA_PATH, {})


def _salvar(dados: dict):
    salvar_json(DATA_PATH, dados)


class Convites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = _ler()
        self.cache_usos = {}

    def _total_de(self, user_id: int) -> int:
        return self.dados.get(str(user_id), 0)

    async def _snapshot(self, guild: discord.Guild) -> dict:
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            print(f"[CONVITES] ⚠️ Sem permissão de 'Gerenciar Servidor' em {guild.name} pra ler os convites.")
            return {}
        return {inv.code: (inv.uses or 0) for inv in invites}


    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            self.cache_usos[guild.id] = await self._snapshot(guild)
        print("[CONVITES] ✅ Cache de convites carregado.")


    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        cache = self.cache_usos.setdefault(invite.guild.id, {})
        cache[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        cache = self.cache_usos.get(invite.guild.id, {})
        cache.pop(invite.code, None)


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        cache_antigo = self.cache_usos.get(guild.id, {})
        cache_novo = await self._snapshot(guild)
        self.cache_usos[guild.id] = cache_novo

        canal = self.bot.get_channel(CANAL_CONVITES_ID)
        if canal is None:
            print(f"[CONVITES] ⚠️ Canal {CANAL_CONVITES_ID} não encontrado.")
            return

        usado = None
        for code, usos_novos in cache_novo.items():
            if usos_novos > cache_antigo.get(code, 0):
                usado = code
                break

        if usado is None:
            await canal.send(f"👋 {member.mention} entrou no servidor, mas não consegui identificar quem convidou.")
            return


        try:
            convite = discord.utils.get(await guild.invites(), code=usado)
        except discord.Forbidden:
            convite = None

        if convite is None or convite.inviter is None:
            await canal.send(f"👋 {member.mention} entrou no servidor, mas não consegui identificar quem convidou.")
            return

        convidador = convite.inviter
        total = self._total_de(convidador.id) + 1
        self.dados[str(convidador.id)] = total
        _salvar(self.dados)

        await canal.send(f"📨 {convidador.mention} convidou {member.mention} e agora tem **{total}** convite(s).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Convites(bot))
