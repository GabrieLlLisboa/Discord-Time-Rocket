"""
Módulo: Cog principal do Sistema de Coaches
Arquivo: cogs/coach_commands.py

Comandos:
  /adicionar-coach  — slash command, só administradores. Cadastra um novo
                       coach (usuário + canal + nome), persistindo em
                       data/coaches_extra.json.
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
from discord import app_commands
from discord.ext import commands

from cogs.coach_config import COACHES, coach_por_channel_id, adicionar_coach, CoachJaExisteError
from cogs.coach_storage import (
    obter_ticket,
    obter_coach_data,
    set_anuncio_coach,
    finalizar_ticket,
    TicketNaoEncontradoError,
    TicketJaFinalizadoError,
)
from cogs.coach_manager import finalizar_atendimento
from cogs.coach_stats import garantir_mensagens_existem, reordenar_mensagens_finais
from cogs.coach_utils import pode_finalizar, eh_gerente
from cogs.coach_anuncios import ANUNCIOS


class Coaches(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mensagens_iniciais_ok = False

    @commands.Cog.listener()
    async def on_ready(self):


        if self._mensagens_iniciais_ok:
            return
        self._mensagens_iniciais_ok = True

        for coach_key in COACHES:
            try:
                await garantir_mensagens_existem(self.bot, coach_key)
            except Exception as e:
                print(f"[COACH] ⚠️ Erro ao garantir mensagens do coach '{coach_key}': {e}")

            try:
                await self._enviar_anuncio_se_preciso(coach_key)
            except Exception as e:
                print(f"[COACH] ⚠️ Erro ao enviar anúncio do coach '{coach_key}': {e}")

    async def _enviar_anuncio_se_preciso(self, coach_key: str) -> None:
        """Envia o texto de divulgação do coach (cogs/coach_anuncios.py) uma
        única vez e recoloca Estatísticas/Comprar como as duas últimas
        mensagens do canal, abaixo do anúncio."""
        texto = ANUNCIOS.get(coach_key)
        if not texto:
            return

        coach_data = await obter_coach_data(coach_key)
        if coach_data.get("anuncio_message_id"):
            return

        coach = COACHES[coach_key]
        canal = self.bot.get_channel(coach["channel_id"])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(coach["channel_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                print(f"[COACH] ⚠️ Canal do coach '{coach_key}' inacessível pra enviar o anúncio: {e}")
                return

        msg = await canal.send(texto)
        await set_anuncio_coach(coach_key, msg.id)
        await reordenar_mensagens_finais(self.bot, coach_key)
        print(f"[COACH] 📣 Anúncio do coach '{coach_key}' enviado no canal {canal.id}.")


    @app_commands.command(name="adicionar-coach", description="Cadastra um novo coach no sistema de atendimentos.")
    @app_commands.describe(
        coach="O usuário que vai ser o coach",
        canal="Canal onde ficam as mensagens de estatísticas/comprar atendimento desse coach",
        nome="Nome de exibição do coach",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def adicionar_coach_cmd(
        self,
        interaction: discord.Interaction,
        coach: discord.Member,
        canal: discord.TextChannel,
        nome: str,
    ):
        try:
            chave = adicionar_coach(coach.id, canal.id, nome)
        except CoachJaExisteError as e:
            await interaction.response.send_message(f"❌ Não deu pra cadastrar: {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Coach **{nome}** cadastrado! Canal: {canal.mention} • Coach: {coach.mention}\n"
            f"As mensagens de estatísticas e o botão de comprar atendimento já vão aparecer lá.",
            ephemeral=True,
        )


        try:
            await garantir_mensagens_existem(self.bot, chave)
        except Exception as e:
            print(f"[COACH] ⚠️ Erro ao criar mensagens iniciais do coach '{chave}': {e}")

        try:
            await self._enviar_anuncio_se_preciso(chave)
        except Exception as e:
            print(f"[COACH] ⚠️ Erro ao enviar anúncio do coach '{chave}': {e}")

        from cogs.coach_views import ComprarAtendimentoView

        self.bot.add_view(ComprarAtendimentoView(chave))

        print(f"[COACH] ✅ Coach '{chave}' ({nome}) cadastrado por {interaction.user} — canal {canal.id}.")

    @adicionar_coach_cmd.error
    async def adicionar_coach_cmd_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem cadastrar coaches.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro ao cadastrar coach: {error}", ephemeral=True)


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


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        info = coach_por_channel_id(message.channel.id)
        if info is None:
            return

        coach_key, _ = info
        try:
            await reordenar_mensagens_finais(self.bot, coach_key)
        except Exception as e:
            print(f"[COACH] ⚠️ Erro ao reordenar mensagens fixas do coach '{coach_key}': {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Coaches(bot))
