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
#    !conversar <id do canal> <o que o bot vai falar>
#    !conversar <o que o bot vai falar> <id da mensagem>
#    !conversar <id do canal> <o que o bot vai falar> <id da mensagem>
#
#  - id do canal: opcional, primeiro "token" da frase — manda a mensagem
#    nesse canal em vez do canal onde o comando foi digitado.
#  - id da mensagem: opcional, último "token" da frase — responde a essa
#    mensagem (procurada no canal de destino) em vez de só mandar solto.
# ─────────────────────────────────────────────

ID_AUTORIZADO = 1487452210605588592
TAMANHO_MINIMO_ID = 15  # IDs do Discord (snowflakes) têm 17-19 dígitos


def _eh_id_valido(token: str) -> bool:
    return token.isdigit() and len(token) >= TAMANHO_MINIMO_ID


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

        texto = argumento.strip()
        canal_alvo = ctx.channel

        # ── 1) Canal opcional: primeiro token da frase ──────────────────────
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

        # ── 2) Mensagem opcional: último token da frase ─────────────────────
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
        # Engole qualquer erro em silêncio — nada de traceback no console,
        # nada de mensagem no canal.
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Conversar(bot))
