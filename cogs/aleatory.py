from __future__ import annotations

import asyncio
import base64
import os
import random

import discord
from discord.ext import commands

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Aleatory
#  Arquivo: cogs/aleatory.py
#  Comando: !aleatory
#
#  Faz o bot ficar mandando mensagens com "cara" de texto criptografado
#  (strings aleatórias em base64/hex) de tempos em tempos no canal.
#  É só visual/diversão — não é uma cifra reversível de verdade, é ruído
#  aleatório gerado com os.urandom.
#
#  Uso:
#   !aleatory                → começa a mandar no canal atual (intervalo padrão 10s)
#   !aleatory <segundos>     → começa com intervalo customizado (mínimo 3s)
#   !aleatory stop           → para de mandar no canal atual
# ─────────────────────────────────────────────────────────────────────────────

INTERVALO_PADRAO = 10
INTERVALO_MINIMO = 3
MAX_MENSAGENS_POR_EXECUCAO = 200  # trava de segurança pra não rodar pra sempre esquecido

PREFIXOS = ["🔒", "🔐", "🛡️", "📡", "🧩"]


def gerar_bloco_criptografado(tamanho: int = 24) -> str:
    """Gera uma string aleatória com 'cara' de texto criptografado (base64 de bytes puramente aleatórios)."""
    dados = os.urandom(tamanho)
    texto = base64.b64encode(dados).decode("utf-8").rstrip("=")
    return texto


class Aleatory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tarefas: dict[int, asyncio.Task] = {}  # channel_id -> task

    async def _loop_envio(self, channel: discord.abc.Messageable, intervalo: int):
        try:
            for _ in range(MAX_MENSAGENS_POR_EXECUCAO):
                prefixo = random.choice(PREFIXOS)
                bloco = gerar_bloco_criptografado(random.randint(16, 32))
                await channel.send(f"{prefixo} `{bloco}`")
                await asyncio.sleep(intervalo)
            await channel.send("⏹️ `!aleatory` parou automaticamente (limite de mensagens da sessão atingido). Use `!aleatory` de novo pra reiniciar.")
        except asyncio.CancelledError:
            raise
        finally:
            self.tarefas.pop(channel.id, None)

    @commands.command(name="aleatory")
    @commands.has_permissions(manage_messages=True)
    async def aleatory(self, ctx: commands.Context, arg: str = None):
        """
        !aleatory              -> começa a mandar mensagens 'criptografadas' aleatórias (a cada 10s)
        !aleatory <segundos>   -> começa com intervalo customizado (mínimo 3s)
        !aleatory stop         -> para
        """
        channel = ctx.channel

        # ── parar ─────────────────────────────────────────────────────────
        if arg and arg.lower() == "stop":
            tarefa = self.tarefas.get(channel.id)
            if tarefa is None:
                return await ctx.send("❌ Não tem nenhum `!aleatory` rodando neste canal.")
            tarefa.cancel()
            self.tarefas.pop(channel.id, None)
            return await ctx.send("⏹️ `!aleatory` parado neste canal.")

        # ── já tem uma rodando aqui? ─────────────────────────────────────
        if channel.id in self.tarefas:
            return await ctx.send("⚠️ Já tem um `!aleatory` rodando neste canal. Use `!aleatory stop` pra parar antes de começar outro.")

        # ── intervalo customizado ────────────────────────────────────────
        intervalo = INTERVALO_PADRAO
        if arg is not None:
            try:
                intervalo = int(arg)
            except ValueError:
                return await ctx.send(f"❌ Uso: `!aleatory`, `!aleatory <segundos>` ou `!aleatory stop`.")
            if intervalo < INTERVALO_MINIMO:
                return await ctx.send(f"❌ O intervalo mínimo é **{INTERVALO_MINIMO}s** (pra não floodar o canal).")

        await ctx.send(
            f"🔐 Começando a mandar mensagens criptografadas aleatórias a cada **{intervalo}s** "
            f"(até {MAX_MENSAGENS_POR_EXECUCAO} msgs ou até alguém mandar `!aleatory stop`)."
        )
        tarefa = asyncio.create_task(self._loop_envio(channel, intervalo))
        self.tarefas[channel.id] = tarefa

    @aleatory.error
    async def aleatory_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Gerenciar Mensagens** pra usar `!aleatory`.")

    def cog_unload(self):
        for tarefa in self.tarefas.values():
            tarefa.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Aleatory(bot))
