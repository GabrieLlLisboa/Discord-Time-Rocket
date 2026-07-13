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

import asyncio

import discord
from discord.ext import commands

from cogs.coach_config import COACHES, coach_por_channel_id
from cogs.coach_storage import (
    obter_ticket,
    finalizar_ticket,
    TicketNaoEncontradoError,
    TicketJaFinalizadoError,
)
from cogs.coach_manager import finalizar_atendimento
from cogs.coach_stats import garantir_mensagens_existem, reordenar_mensagens_finais
from cogs.coach_utils import pode_finalizar, eh_gerente


class Coaches(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mensagens_iniciais_ok = False

    @commands.Cog.listener()
    async def on_ready(self):
        # cog_load() roda ANTES do bot se conectar ao Discord (main.py chama
        # load_cogs() antes de bot.start()), então qualquer chamada à API
        # feita ali (como buscar o canal do coach) falharia sempre. on_ready
        # só dispara depois que o bot já está conectado e autenticado — por
        # isso a criação das mensagens fixas mora aqui. A trava evita
        # recriar tudo de novo caso on_ready dispare mais de uma vez
        # (reconexão/RESUME).
        if self._mensagens_iniciais_ok:
            return
        self._mensagens_iniciais_ok = True

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

    # ── Comando de encerramento forçado (staff/adm) ──────────────────────
    @commands.command(name="acabar-coach")
    async def acabar_coach(self, ctx: commands.Context):
        """Uso: staff/adm digita !acabar-coach DENTRO do canal do
        atendimento. Apaga o canal do ticket e o canal de voz associado,
        sem esperar o cliente avaliar."""
        canal = ctx.channel
        ticket = await obter_ticket(canal.id)

        if ticket is None:
            await ctx.send("❌ Este comando só pode ser usado dentro de um canal de atendimento de coach.")
            return

        if not eh_gerente(ctx.author):
            await ctx.send("❌ Apenas staff/administração pode usar este comando.")
            return

        # Mantém os dados do ticket consistentes (marca como concluído,
        # se ainda não estava) antes de apagar os canais
        try:
            await finalizar_ticket(canal.id)
        except (TicketNaoEncontradoError, TicketJaFinalizadoError):
            pass

        canal_voz_id = ticket.get("canal_voz_id")
        canal_voz = ctx.guild.get_channel(canal_voz_id) if canal_voz_id else None

        await ctx.send("🗑️ Encerrando o atendimento — este canal e o canal de voz vão ser apagados em alguns segundos.")
        await asyncio.sleep(5)

        if canal_voz is not None:
            try:
                await canal_voz.delete(reason=f"Atendimento encerrado via !acabar-coach por {ctx.author}")
            except discord.HTTPException as e:
                print(f"[COACH] ⚠️ Erro ao apagar canal de voz do ticket {canal.id}: {e}")

        print(f"[COACH] 🗑️ Ticket {canal.id} encerrado via !acabar-coach por {ctx.author}.")

        try:
            await canal.delete(reason=f"Atendimento encerrado via !acabar-coach por {ctx.author}")
        except discord.HTTPException as e:
            print(f"[COACH] ⚠️ Erro ao apagar canal do ticket {canal.id}: {e}")

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
