import discord
from discord.ext import commands

# ─────────────────────────────────────────────
#  Cog: Comando oculto "conversar"
#  Arquivo: cogs/conversar.py
#
#  Comando de PREFIXO (não é slash — por isso nunca aparece na lista
#  de "/" do Discord nem precisa de sync). Fica escondido do !help
#  (hidden=True) e não gera NENHUM registro: não manda nada pro canal
#  de logs (cogs/logs.py só reage a eventos do próprio Discord, e esse
#  comando não apaga/edita mensagens), não dá print no console e
#  engole qualquer erro em silêncio.
#
#  Só o usuário com o ID abaixo pode usar. Qualquer outra pessoa que
#  tentar não recebe resposta nenhuma (nem erro, nem aviso) — pra
#  quem não é o dono nem dá pra perceber que o comando existe.
#
#  Uso:
#    !conversar <o que o bot vai falar>
#    !conversar <o que o bot vai falar> <id da mensagem>   (responde a ela)
# ─────────────────────────────────────────────

ID_AUTORIZADO = 1487452210605588592


class Conversar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="conversar", hidden=True)
    async def conversar(self, ctx: commands.Context, *, argumento: str = None):
        # Não é o dono? Ignora completamente, sem dar nenhum sinal de que
        # o comando existe.
        if ctx.author.id != ID_AUTORIZADO:
            return

        if not argumento or not argumento.strip():
            return

        texto = argumento
        mensagem_alvo = None

        # Se a última "palavra" for um número grande (jeitão de ID de
        # mensagem do Discord), tenta usar como o ID a responder.
        partes = argumento.rsplit(" ", 1)
        if len(partes) == 2 and partes[1].isdigit() and len(partes[1]) >= 15:
            possivel_texto, possivel_id = partes[0], partes[1]
            try:
                mensagem_alvo = await ctx.channel.fetch_message(int(possivel_id))
                texto = possivel_texto
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Não achou a mensagem — trata o argumento inteiro como texto.
                mensagem_alvo = None
                texto = argumento

        if not texto.strip():
            return

        try:
            if mensagem_alvo is not None:
                await mensagem_alvo.reply(texto, mention_author=False)
            else:
                await ctx.send(texto)
        except discord.HTTPException:
            pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Engole qualquer erro em silêncio — nada de traceback no console,
        # nada de mensagem no canal.
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Conversar(bot))
