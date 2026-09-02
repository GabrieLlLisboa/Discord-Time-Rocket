"""
Módulo: Modals do Sistema de Coaches
Arquivo: cogs/coach_modals.py
"""

from __future__ import annotations

import discord


class ComentarioModal(discord.ui.Modal, title="Avaliar Atendimento"):
    comentario = discord.ui.TextInput(
        label="O que achou do atendimento?",
        style=discord.TextStyle.long,
        placeholder="Conte como foi seu atendimento...",
        required=True,
        max_length=1000,
    )

    def __init__(self, canal_ticket_id: int, nota: int):
        super().__init__()
        self.canal_ticket_id = canal_ticket_id
        self.nota = nota

    async def on_submit(self, interaction: discord.Interaction):
        # Import local para evitar import circular (coach_manager também
        # depende, indiretamente, de módulos que importam views/selects).
        from cogs.coach_manager import concluir_avaliacao

        await concluir_avaliacao(interaction, self.canal_ticket_id, self.nota, str(self.comentario))

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"[COACH_MODAL] ❌ Erro ao processar avaliação: {error}")
        mensagem = "❌ Ocorreu um erro ao registrar sua avaliação. Tente novamente."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)
        except discord.HTTPException:
            pass
