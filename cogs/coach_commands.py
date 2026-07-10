"""
Módulo: Cog principal do Sistema de Coaches
Arquivo: cogs/coach_commands.py

Comandos:
  !finalizar-coach  — usado DENTRO do canal do ticket, por: coach
                       responsável ou staff/gerência.

Também mantém, via listener on_message, a garantia de que as mensagens
"📊 Estatísticas" e "🛒 Comprar Atendimento" continuem sendo sempre as
duas últimas do canal de cada coach — mesmo que alguém escreva algo ali
manualmente.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from cogs.coach_config import COACHES, coach_por_channel_id
from cogs.coach_storage import (
    obter_ticket,
    TicketNaoEncontradoError,
    TicketJaFinalizadoError,
)
from cogs.coach_manager import finalizar_atendimento
from cogs.coach_stats import garantir_mensagens_existem, reordenar_mensagens_finais
from cogs.coach_utils import pode_finalizar


class Coaches(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Garante que todo coach configurado tenha as duas mensagens fixas
        # no canal (cria se estiver faltando — ex: primeira vez rodando,
        # ou mensagens apagadas enquanto o bot estava offline).
        for coach_key in COACHES:
            try:
                await garantir_mensagens_existem(self.bot, coach_key)
            except Exception as e:
                print(f"[COACH] ⚠️ Erro ao garantir mensagens do coach '{coach_key}': {e}")

    # ── Comando de finalização ───────────────────────────────────────────
    @commands.command(name="finalizar-coach")
    async def finalizar_coach(self, ctx: commands.Context):
        canal = ctx.channel
        ticket = await obter_ticket(canal.id)

        if ticket is None:
            await ctx.send("❌ Este comando só pode ser usado dentro de um canal de atendimento de coach.")
            return

        if not pode_finalizar(ctx.author, ticket["coach_key"]):
            await ctx.send("❌ Você não possui permissão para finalizar este atendimento.")
            return

        try:
            await finalizar_atendimento(canal)
        except TicketNaoEncontradoError:
            await ctx.send("❌ Este atendimento não foi encontrado.")
        except TicketJaFinalizadoError:
            await ctx.send("⚠️ Este atendimento já foi finalizado anteriormente.")
        else:
            await ctx.message.add_reaction("✅")
            print(f"[COACH] ✅ Ticket {canal.id} finalizado por {ctx.author}.")

    # ── Garante a ordem das mensagens fixas no canal do coach ───────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return  # ignora mensagens do próprio bot (evita loop com o reorder abaixo)

        info = coach_por_channel_id(message.channel.id)
        if info is None:
            return  # não é um canal de coach

        coach_key, _ = info
        try:
            await reordenar_mensagens_finais(self.bot, coach_key)
        except Exception as e:
            print(f"[COACH] ⚠️ Erro ao reordenar mensagens fixas do coach '{coach_key}': {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Coaches(bot))
