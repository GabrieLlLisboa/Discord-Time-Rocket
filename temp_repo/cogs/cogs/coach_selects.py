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

        # Revalida no momento da escolha — o cliente pode ter deixado essa
        # mensagem ephemeral aberta e clicado em "Avaliar" em outra aba, ou
        # o ticket pode ter sido avaliado por outro caminho nesse meio tempo.
        ticket = await obter_ticket(self.canal_ticket_id)
        if ticket is None or ticket.get("avaliado"):
            await interaction.response.send_message(
                "⚠️ Você já avaliou este atendimento (ou ele não existe mais).",
                ephemeral=True,
            )
            return

        nota = int(self.values[0])
        await interaction.response.send_modal(ComentarioModal(self.canal_ticket_id, nota))
        # OBS: não dá pra desabilitar o select depois daqui — o send_modal
        # já consumiu a resposta desta interação, então não existe mais
        # "mensagem original" pra editar (interaction.edit_original_response
        # sempre falharia). A proteção contra reenvio duplicado já é feita
        # no início deste callback e em coach_manager.concluir_avaliacao
        # (via TicketJaAvaliadoError), então não é necessário aqui.


class NotaSelectView(discord.ui.View):
    def __init__(self, canal_ticket_id: int):
        super().__init__(timeout=300)
        self.add_item(NotaSelect(canal_ticket_id))
