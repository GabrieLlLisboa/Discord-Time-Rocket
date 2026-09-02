import discord
from discord.ext import commands

from cogs.players import CARGOS_RANK, RANK_IDS, CARGO_MAP

# ─────────────────────────────────────────────
#  Cog: Enquete de Divisão
#  Arquivo: cogs/div_poll.py
#
#  Comando !div — lança uma enquete onde cada jogador escolhe o rank e a
#  divisão que joga atualmente (ex: Diamante 2, Platina 3...). Assim que a
#  pessoa responde, o cargo de rank correspondente é aplicado
#  automaticamente (trocando qualquer rank antigo que ela já tivesse) —
#  sem precisar de aprovação da staff.
#
#  A enquete não guarda "votos" à parte: o placar mostrado é sempre a
#  contagem real de quem tem cada cargo no servidor, então nunca fica
#  desincronizado.
# ─────────────────────────────────────────────

DIV_SELECT_CUSTOM_ID = "div_poll_selecionar_rank"


def build_div_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🎮 Enquete de Divisão — Rocket League",
        description=(
            "Escolha abaixo o **rank e a divisão** que você joga atualmente.\n"
            "O cargo é aplicado **automaticamente** assim que você escolher — "
            "e substitui qualquer rank antigo que você já tinha. 👇"
        ),
        color=0xD4A843,
    )
    for c in CARGOS_RANK:
        cargo = guild.get_role(c["id"])
        qtd = len(cargo.members) if cargo else 0
        embed.add_field(name=f"{c['emoji']} {c['nome']}", value=f"`{qtd} jogador(es)`", inline=True)
    embed.set_footer(text="Sua escolha atualiza automaticamente o seu cargo de rank.")
    embed.timestamp = discord.utils.utcnow()
    return embed


class DivSelect(discord.ui.Select):
    def __init__(self):
        opcoes = [
            discord.SelectOption(label=c["nome"], value=str(c["id"]), emoji=c["emoji"])
            for c in CARGOS_RANK
        ]
        super().__init__(
            placeholder="Selecione seu rank e divisão atual...",
            options=opcoes,
            custom_id=DIV_SELECT_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        novo_id = int(self.values[0])
        novo_info = CARGO_MAP.get(novo_id)
        novo_cargo = interaction.guild.get_role(novo_id)
        if novo_cargo is None or novo_info is None:
            await interaction.followup.send(
                "⚠️ Esse cargo não existe mais no servidor. Chama a staff!", ephemeral=True
            )
            return

        membro = interaction.user
        cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS and r.id != novo_cargo.id]

        try:
            if cargos_rank_atuais:
                await membro.remove_roles(*cargos_rank_atuais, reason="Enquete de divisão (!div)")
            if novo_cargo not in membro.roles:
                await membro.add_roles(novo_cargo, reason="Enquete de divisão (!div)")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão pra alterar seu cargo. Chama a staff!", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Prontinho! Seu rank agora é {novo_info['emoji']} **{novo_info['nome']}**.",
            ephemeral=True,
        )

        try:
            embed = build_div_embed(interaction.guild)
            await interaction.message.edit(embed=embed)
        except discord.HTTPException:
            pass


class DivView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DivSelect())


class DivPoll(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(DivView())

    @commands.command(name="div")
    @commands.has_permissions(administrator=True)
    async def div_cmd(self, ctx: commands.Context):
        """Lança a enquete de divisão neste canal."""
        embed = build_div_embed(ctx.guild)
        await ctx.send(embed=embed, view=DivView())

    @div_cmd.error
    async def div_cmd_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem lançar a enquete de divisão.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(DivPoll(bot))
