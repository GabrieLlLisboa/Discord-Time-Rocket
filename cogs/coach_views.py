"""
Módulo: Views Persistentes do Sistema de Coaches
Arquivo: cogs/coach_views.py

Três views persistentes (timeout=None + custom_id fixo, registradas em
main.py via bot.add_view — funcionam mesmo após restart, sem precisar
reenviar as mensagens):

  ComprarAtendimentoView -> uma instância por coach (custom_id inclui a
                             chave do coach, ex: "coach_comprar:isaque")
  CancelarCoachView      -> uma instância por ticket ainda "Em andamento"
                             (custom_id inclui o id do canal do ticket, ex:
                             "coach_cancelar:123456789") — só o cliente ou
                             o coach responsável podem apertar.
  AvaliarCoachView       -> uma instância por ticket finalizado e ainda não
                             avaliado (custom_id inclui o id do canal do
                             ticket, ex: "coach_avaliar:123456789")
"""

from __future__ import annotations

import discord

from cogs.coach_config import coach_por_chave


class ComprarAtendimentoView(discord.ui.View):
    def __init__(self, coach_key: str):
        super().__init__(timeout=None)
        self.coach_key = coach_key
        # custom_id só é conhecido em runtime (depende do coach) — por isso
        # o botão é criado aqui no __init__ e adicionado manualmente, em vez
        # de usar o decorator @discord.ui.button (que fixa o custom_id em
        # tempo de definição da classe).
        botao = discord.ui.Button(
            label="🛒 Comprar Atendimento",
            style=discord.ButtonStyle.success,
            custom_id=f"coach_comprar:{coach_key}",
        )
        botao.callback = self._callback
        self.add_item(botao)

    async def _callback(self, interaction: discord.Interaction):
        # Import local para evitar import circular (coach_manager importa
        # coach_stats, que importa esta view de volta).
        from cogs.coach_manager import criar_ticket_atendimento

        await criar_ticket_atendimento(interaction, self.coach_key)


class CancelarCoachView(discord.ui.View):
    def __init__(self, canal_ticket_id: int):
        super().__init__(timeout=None)
        self.canal_ticket_id = canal_ticket_id
        botao = discord.ui.Button(
            label="🚫 Cancelar Atendimento",
            style=discord.ButtonStyle.danger,
            custom_id=f"coach_cancelar:{canal_ticket_id}",
        )
        botao.callback = self._callback
        self.add_item(botao)

    async def _callback(self, interaction: discord.Interaction):
        import asyncio

        from cogs.coach_storage import (
            obter_ticket,
            TicketNaoEncontradoError,
            TicketJaFinalizadoError,
            TicketJaCanceladoError,
        )
        from cogs.coach_utils import eh_coach_responsavel
        from cogs.coach_manager import cancelar_atendimento

        ticket = await obter_ticket(self.canal_ticket_id)
        if ticket is None:
            await interaction.response.send_message(
                "❌ Este atendimento não foi encontrado (pode ter sido removido).",
                ephemeral=True,
            )
            return

        eh_cliente = ticket["cliente_id"] == interaction.user.id
        eh_coach = eh_coach_responsavel(interaction.user, ticket["coach_key"])
        if not (eh_cliente or eh_coach):
            await interaction.response.send_message(
                "❌ Somente o cliente ou o coach deste atendimento podem cancelá-lo.",
                ephemeral=True,
            )
            return

        if ticket["status"] == "Concluído":
            await interaction.response.send_message(
                "❌ Este atendimento já foi finalizado — não pode mais ser cancelado.",
                ephemeral=True,
            )
            return

        if ticket["status"] == "Cancelado":
            await interaction.response.send_message(
                "⚠️ Este atendimento já foi cancelado.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🚫 Atendimento cancelado — este canal será apagado em alguns segundos."
        )

        try:
            await cancelar_atendimento(interaction.channel)
        except (TicketNaoEncontradoError, TicketJaFinalizadoError, TicketJaCanceladoError):
            pass

        canal = interaction.channel
        await asyncio.sleep(5)
        try:
            await canal.delete(reason=f"Atendimento cancelado por {interaction.user}")
        except discord.HTTPException as e:
            print(f"[COACH] ⚠️ Erro ao apagar canal do ticket {self.canal_ticket_id} após cancelamento: {e}")


class AvaliarCoachView(discord.ui.View):
    def __init__(self, canal_ticket_id: int):
        super().__init__(timeout=None)
        self.canal_ticket_id = canal_ticket_id
        botao = discord.ui.Button(
            label="⭐ Avaliar Coach",
            style=discord.ButtonStyle.primary,
            custom_id=f"coach_avaliar:{canal_ticket_id}",
        )
        botao.callback = self._callback
        self.add_item(botao)

    async def _callback(self, interaction: discord.Interaction):
        from cogs.coach_storage import obter_ticket
        from cogs.coach_selects import NotaSelectView

        ticket = await obter_ticket(self.canal_ticket_id)
        if ticket is None:
            await interaction.response.send_message(
                "❌ Este atendimento não foi encontrado (pode ter sido removido).",
                ephemeral=True,
            )
            return

        if ticket["cliente_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Somente o cliente que abriu este atendimento pode avaliá-lo.",
                ephemeral=True,
            )
            return

        if ticket["avaliado"]:
            await interaction.response.send_message(
                "⚠️ Você já avaliou este atendimento.",
                ephemeral=True,
            )
            return

        if ticket["status"] != "Concluído":
            await interaction.response.send_message(
                "❌ Este atendimento ainda não foi finalizado.",
                ephemeral=True,
            )
            return

        coach = coach_por_chave(ticket["coach_key"])
        nome_coach = coach["nome"] if coach else ticket["coach_key"]

        # A API do Discord não permite Select dentro de Modal nesta versão
        # do discord.py — por isso a avaliação é feita em duas etapas:
        # 1) o cliente escolhe a nota num Select (ephemeral); 2) ao
        # selecionar, abrimos o Modal só com o campo de comentário.
        await interaction.response.send_message(
            f"Avaliando o atendimento com **{nome_coach}** — selecione a nota:",
            view=NotaSelectView(self.canal_ticket_id),
            ephemeral=True,
        )
