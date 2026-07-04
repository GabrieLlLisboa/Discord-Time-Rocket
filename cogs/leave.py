import discord
from discord.ext import commands
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Despedida (saída de membros)
#  Arquivo: cogs/leave.py
#  Evento: on_member_remove
# ─────────────────────────────────────────────

LEAVE_CHANNEL_ID = 1522984476450361364

COR_DESPEDIDA = 0x992D22  # vermelho escuro — propositalmente bem diferente do dourado de boas-vindas


def _tempo_no_servidor(entrou_em) -> str:
    if entrou_em is None:
        return "desconhecido"
    agora = datetime.now(timezone.utc)
    delta = agora - entrou_em
    dias = delta.days

    if dias >= 365:
        anos, resto = divmod(dias, 365)
        texto = f"{anos} ano(s)"
        if resto:
            texto += f" e {resto} dia(s)"
        return texto
    if dias >= 30:
        meses, resto = divmod(dias, 30)
        texto = f"{meses} mês(es)"
        if resto:
            texto += f" e {resto} dia(s)"
        return texto
    if dias >= 1:
        return f"{dias} dia(s)"

    horas = delta.seconds // 3600
    return f"{horas} hora(s)" if horas else "menos de 1 hora"


# ── Modal pra deixar um recado de despedida ─────────────────────────────────
class DespedidaModal(discord.ui.Modal, title="Deixar um recado"):
    mensagem = discord.ui.TextInput(
        label="Sua mensagem de despedida",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Foi ótimo jogar com você, boa sorte por aí!",
        max_length=200,
    )

    def __init__(self, nome_de_quem_saiu: str):
        super().__init__()
        self.nome_de_quem_saiu = nome_de_quem_saiu

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            description=(
                f"💌 **{interaction.user.display_name}** deixou um recado pra "
                f"**{self.nome_de_quem_saiu}**:\n\n*\"{self.mensagem}\"*"
            ),
            color=COR_DESPEDIDA,
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Recado enviado!", ephemeral=True)


# ── View com o botão de recado (custom_id guarda o ID de quem saiu) ─────────
class DespedidaView(discord.ui.View):
    def __init__(self, membro_id: int):
        super().__init__(timeout=None)
        self.membro_id = membro_id
        self.deixar_recado.custom_id = f"despedida_recado:{membro_id}"

    @discord.ui.button(label="💌 Deixar um recado", style=discord.ButtonStyle.secondary)
    async def deixar_recado(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            usuario = await interaction.client.fetch_user(self.membro_id)
            nome = usuario.name
        except discord.NotFound:
            nome = "essa pessoa"
        await interaction.response.send_modal(DespedidaModal(nome))


class Despedida(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = self.bot.get_channel(LEAVE_CHANNEL_ID)
        if channel is None:
            print(f"[LEAVE] ⚠️  Canal {LEAVE_CHANNEL_ID} não encontrado.")
            return

        guild = member.guild
        tempo = _tempo_no_servidor(member.joined_at)

        embed = discord.Embed(
            title="💔 Mais um saiu do clube...",
            description=f"**{member}** deixou a **{guild.name}**. Sentiremos falta! 🕊️",
            color=COR_DESPEDIDA,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="⏳ Tempo no servidor",  value=tempo, inline=True)
        embed.add_field(name="👥 Membros restantes",  value=f"`{guild.member_count}`", inline=True)
        embed.add_field(
            name="📅 Saiu em",
            value=discord.utils.format_dt(datetime.now(timezone.utc), style="f"),
            inline=True,
        )

        embed.set_footer(
            text=f"{guild.name}",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
        )

        await channel.send(embed=embed, view=DespedidaView(member.id))
        print(f"[LEAVE] ✅ Mensagem de saída enviada para {member} no canal #{channel.name}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Despedida(bot))
