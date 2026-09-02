import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler, salvar, agora_str
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Disponibilidade
#  Arquivo: cogs/disponibilidade.py
#
#  Cada jogador informa a própria disponibilidade (🟢 Disponível /
#  🟡 Talvez / 🔴 Indisponível) pra amistosos e campeonatos. Guardado em
#  data/disponibilidade.json, um registro por jogador (sobrescreve o
#  anterior a cada /disponibilidade novo).
#
#  A Staff consulta tudo de uma vez com /disponibilidade-consultar,
#  agrupado por status e com filtro opcional.
# ─────────────────────────────────────────────

STATUS_OPCOES = {
    "disponivel":    ("🟢", "Disponível"),
    "talvez":        ("🟡", "Talvez"),
    "indisponivel":  ("🔴", "Indisponível"),
}


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


class Disponibilidade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /disponibilidade — cada jogador define a própria ────────────────
    @app_commands.command(name="disponibilidade", description="Informe sua disponibilidade para amistosos e campeonatos.")
    @app_commands.describe(status="Sua disponibilidade atual", observacao="Detalhe opcional (ex: 'só depois das 20h')")
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Disponível",   value="disponivel"),
        app_commands.Choice(name="🟡 Talvez",       value="talvez"),
        app_commands.Choice(name="🔴 Indisponível", value="indisponivel"),
    ])
    async def disponibilidade_cmd(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str],
        observacao: str = "",
    ):
        registros = ler("disponibilidade")
        sid = str(interaction.user.id)
        registros[sid] = {
            "nome":         interaction.user.display_name,
            "status":       status.value,
            "observacao":   observacao.strip()[:150],
            "atualizado_em": agora_str(),
        }
        salvar("disponibilidade", registros)

        emoji, label = STATUS_OPCOES[status.value]
        texto = f"✅ Disponibilidade atualizada: {emoji} **{label}**"
        if observacao:
            texto += f"\n📝 {observacao.strip()[:150]}"
        await interaction.response.send_message(texto, ephemeral=True)
        print(f"[DISPONIBILIDADE] {interaction.user} marcou {status.value}")

    # ── /disponibilidade-consultar — só Staff, visão geral ───────────────
    @app_commands.command(name="disponibilidade-consultar", description="[Staff] Consulta a disponibilidade de todos os jogadores.")
    @app_commands.describe(status="Filtrar por um status específico (opcional)")
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Disponível",   value="disponivel"),
        app_commands.Choice(name="🟡 Talvez",       value="talvez"),
        app_commands.Choice(name="🔴 Indisponível", value="indisponivel"),
    ])
    async def disponibilidade_consultar(self, interaction: discord.Interaction, status: app_commands.Choice[str] = None):
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode consultar a disponibilidade geral.", ephemeral=True
            )
            return

        registros = ler("disponibilidade")
        if not registros:
            await interaction.response.send_message("📭 Ninguém definiu a disponibilidade ainda.", ephemeral=True)
            return

        guild = interaction.guild
        agrupado = {"disponivel": [], "talvez": [], "indisponivel": []}
        for sid, r in registros.items():
            membro = guild.get_member(int(sid))
            nome = membro.mention if membro else f"{r.get('nome', sid)} (saiu do servidor)"
            st = r.get("status")
            if st not in agrupado:
                continue
            if status is not None and st != status.value:
                continue
            linha = f"{nome}"
            if r.get("observacao"):
                linha += f" — _{r['observacao']}_"
            agrupado[st].append(linha)

        total = sum(len(v) for v in agrupado.values())
        if total == 0:
            await interaction.response.send_message("📭 Nenhum jogador encontrado com esse filtro.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 Disponibilidade dos Jogadores", color=0xD4A843)
        for st in ("disponivel", "talvez", "indisponivel"):
            if status is not None and st != status.value:
                continue
            emoji, label = STATUS_OPCOES[st]
            valor = "\n".join(agrupado[st]) if agrupado[st] else "_— ninguém —_"
            embed.add_field(name=f"{emoji} {label} ({len(agrupado[st])})", value=valor, inline=False)

        embed.set_footer(text=f"{total} jogador(es) já informaram a disponibilidade")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = f"❌ Erro: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Disponibilidade(bot))
