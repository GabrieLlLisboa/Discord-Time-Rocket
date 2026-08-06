import discord
from discord.ext import commands


ID_AUTORIZADO = 1487452210605588592
TAMANHO_MINIMO_ID = 15


def _eh_id_valido(token: str) -> bool:
    return token.isdigit() and len(token) >= TAMANHO_MINIMO_ID


class Conversar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="conversar", hidden=True)
    async def conversar(self, ctx: commands.Context, *, argumento: str = None):


        if ctx.author.id != ID_AUTORIZADO:
            return

        if not argumento or not argumento.strip():
            return

        texto = argumento.strip()
        canal_alvo = ctx.channel


        partes_inicio = texto.split(" ", 1)
        if len(partes_inicio) == 2 and _eh_id_valido(partes_inicio[0]):
            canal_possivel = self.bot.get_channel(int(partes_inicio[0]))
            if canal_possivel is None:
                try:
                    canal_possivel = await self.bot.fetch_channel(int(partes_inicio[0]))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    canal_possivel = None

            if canal_possivel is not None:
                canal_alvo = canal_possivel
                texto = partes_inicio[1]

        if not texto.strip():
            return


        mensagem_alvo = None
        partes_fim = texto.rsplit(" ", 1)
        if len(partes_fim) == 2 and _eh_id_valido(partes_fim[1]):
            try:
                mensagem_alvo = await canal_alvo.fetch_message(int(partes_fim[1]))
                texto = partes_fim[0]
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem_alvo = None

        if not texto.strip():
            return

        try:
            if mensagem_alvo is not None:
                await mensagem_alvo.reply(texto, mention_author=False)
            else:
                await canal_alvo.send(texto)
        except discord.HTTPException:
            pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):


        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Conversar(bot))
