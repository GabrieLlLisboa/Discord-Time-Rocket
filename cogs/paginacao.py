import discord

# ─────────────────────────────────────────────
#  Utilitário: Paginação genérica
#  Arquivo: cogs/paginacao.py
# ─────────────────────────────────────────────

class PaginacaoView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed], ephemeral: bool = False):
        super().__init__(timeout=120)
        self.embeds   = embeds
        self.pagina   = 0
        self.ephemeral = ephemeral
        self._atualizar_botoes()

    def _atualizar_botoes(self):
        self.anterior.disabled = self.pagina == 0
        self.proximo.disabled  = self.pagina == len(self.embeds) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pagina -= 1
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.embeds[self.pagina], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def proximo(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pagina += 1
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.embeds[self.pagina], view=self)


def paginar(itens: list, por_pagina: int, montar_embed) -> list[discord.Embed]:
    """
    Divide uma lista em páginas e chama montar_embed(pagina, itens_da_pagina, offset).
    offset = índice global do primeiro item da página.
    """
    embeds = []
    total_paginas = max(1, (len(itens) + por_pagina - 1) // por_pagina)
    for p in range(total_paginas):
        inicio  = p * por_pagina
        fim     = inicio + por_pagina
        fatia   = itens[inicio:fim]
        embed   = montar_embed(p + 1, total_paginas, fatia, inicio)
        embeds.append(embed)
    return embeds
