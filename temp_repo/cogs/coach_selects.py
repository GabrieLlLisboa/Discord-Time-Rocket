"""
Módulo: Selects do Sistema de Coaches
Arquivo: cogs/coach_selects.py

NotaSelectView é a primeira etapa da avaliação (ver coach_views.py ->
AvaliarCoachView): um Select ephemeral com as opções de 1 a 5 estrelas.
Ao escolher, abre o Modal de comentário (coach_modals.py). Não é
persistente (não sobrevive a um restart do bot) porque é apenas um passo
intermediário de poucos segundos dentro de uma única interação do
usuário — se o bot reiniciar nesse meio tempo, o cliente simplesmente
clica em "⭐ Avaliar Coach" de novo.
"""

from __future__ import annotations

import discord

OPCOES_NOTA = [
    discord.SelectOption(label="⭐", value="1"),
    discord.SelectOption(label="⭐⭐", value="2"),
    discord.SelectOption(label="⭐⭐⭐", value="3"),
    discord.SelectOption(label="⭐⭐⭐⭐", value="4"),
    discord.SelectOption(label="⭐⭐⭐⭐⭐", value="5"),
]


class NotaSelect(discord.ui.Select):
    def __init__(self, canal_ticket_id: int):
        self.canal_ticket_id = canal_ticket_id
        super().__init__(
            placeholder="Selecione a nota...",
            min_values=1,
            max_values=1,
            options=OPCOES_NOTA,
        )

    async def callback(self, interaction: discord.Interaction):
        from cogs.coach_modals import ComentarioModal
        from cogs.coach_storage import obter_ticket


        ticket = await obter_ticket(self.canal_ticket_id)
        if ticket is None or ticket.get("avaliado"):
            await interaction.response.send_message(
                "⚠️ Você já avaliou este atendimento (ou ele não existe mais).",
                ephemeral=True,
            )
            return

        nota = int(self.values[0])
        await interaction.response.send_modal(ComentarioModal(self.canal_ticket_id, nota))


class NotaSelectView(discord.ui.View):
    def __init__(self, canal_ticket_id: int):
        super().__init__(timeout=300)
        self.add_item(NotaSelect(canal_ticket_id))
