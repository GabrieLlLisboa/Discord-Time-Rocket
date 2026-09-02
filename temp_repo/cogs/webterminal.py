import asyncio
import re
import sys
import threading

import discord
from discord.ext import commands, tasks

import console as console_local


CANAL_TERMINAL_ID = 1534197342922735679


INTERVALO_FLUSH_SEGUNDOS = 1.5


TAMANHO_MAX_BLOCO = 1900

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class _TerminalTee:
    """Espelha tudo que é escrito num stream (stdout/stderr) também pra um
    buffer em memória (thread-safe), que depois é mandado pro canal do
    Discord. Continua escrevendo normalmente no stream original também,
    então o terminal de verdade continua funcionando igual."""

    def __init__(self, original):
        self._original = original
        self._buffer: list[str] = []
        self._lock = threading.Lock()

    def write(self, texto: str):
        self._original.write(texto)
        if texto and texto.strip():
            limpo = _ANSI_RE.sub("", texto)
            with self._lock:
                self._buffer.append(limpo)
        return len(texto)

    def flush(self):
        self._original.flush()

    def isatty(self):
        return getattr(self._original, "isatty", lambda: False)()

    def coletar(self) -> str:
        with self._lock:
            if not self._buffer:
                return ""
            texto = "".join(self._buffer)
            self._buffer.clear()
        return texto


_instancia: "WebTerminal | None" = None


async def forcar_flush():
    """Manda pro Discord, na hora, o que ainda estiver no buffer. Chamado
    pelo console.py um instante antes de fechar ou reiniciar o processo,
    pra não perder as últimas linhas (ex: 'Reiniciando...')."""
    if _instancia is not None:
        await _instancia._flush()


class WebTerminal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        global _instancia
        self.bot = bot
        self.tee_out = self._instalar_tee_em(sys, "stdout")
        self.tee_err = self._instalar_tee_em(sys, "stderr")
        _instancia = self
        self.flush_loop.start()

    @staticmethod
    def _instalar_tee_em(modulo, nome_attr: str) -> _TerminalTee:
        atual = getattr(modulo, nome_attr)
        if isinstance(atual, _TerminalTee):
            return atual
        tee = _TerminalTee(atual)
        setattr(modulo, nome_attr, tee)
        return tee

    def cog_unload(self):
        self.flush_loop.cancel()


    @tasks.loop(seconds=INTERVALO_FLUSH_SEGUNDOS)
    async def flush_loop(self):
        await self._flush()

    @flush_loop.before_loop
    async def _antes_do_loop(self):
        await self.bot.wait_until_ready()

    async def _flush(self):
        texto = self.tee_out.coletar() + self.tee_err.coletar()
        if not texto.strip():
            return

        canal = self.bot.get_channel(CANAL_TERMINAL_ID)
        if canal is None:
            return

        await self._mandar_em_blocos(canal, texto)

    async def _mandar_em_blocos(self, canal: discord.abc.Messageable, texto: str):
        blocos = []
        bloco = ""
        for linha in texto.splitlines():
            linha = linha[:TAMANHO_MAX_BLOCO]
            if len(bloco) + len(linha) + 1 > TAMANHO_MAX_BLOCO:
                blocos.append(bloco)
                bloco = ""
            bloco += linha + "\n"
        if bloco:
            blocos.append(bloco)

        for b in blocos:
            try:
                await canal.send(f"```{b[:TAMANHO_MAX_BLOCO]}```")
            except discord.HTTPException:
                pass


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != CANAL_TERMINAL_ID:
            return
        if not isinstance(message.author, discord.Member) or not message.author.guild_permissions.administrator:
            return

        comando = message.content.strip()
        if not comando or comando.startswith("```"):
            return

        try:
            await message.add_reaction("⏳")
        except discord.HTTPException:
            pass

        print(f"[WEBTERMINAL] 💻 Comando recebido de {message.author} (#{message.author.id}): {comando}")
        conhecido = await console_local.executar_comando(self.bot, comando)

        if not conhecido:
            await message.channel.send(
                f"❓ Comando desconhecido: `{comando}`.\n```{console_local.COMANDOS_AJUDA}```"
            )
            try:
                await message.add_reaction("❓")
            except discord.HTTPException:
                pass
            return

        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WebTerminal(bot))
