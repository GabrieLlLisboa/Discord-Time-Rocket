import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str

# ─────────────────────────────────────────────
#  Cog: Resultados
#  Arquivo: cogs/resultados.py
#  /resultado — registra vitória/derrota de amistoso
#  /ranking   — placar geral acumulado
# ─────────────────────────────────────────────

ADMIN_ROLE_ID        = 1511894837790769204
AMISTOSOS_CHANNEL_ID = 1514778555970621531


class Resultados(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /resultado ────────────────────────────────────────────────────────────
    @app_commands.command(name="resultado", description="Registra o resultado de um amistoso.")
    @app_commands.checks.has_role(ADMIN_ROLE_ID)
    @app_commands.describe(
        adversario="Nome do adversário (como foi anunciado)",
        resultado="Resultado do amistoso",
        placar="Placar final (ex: 3-1)",
    )
    @app_commands.choices(resultado=[
        app_commands.Choice(name="✅ Vitória",  value="vitoria"),
        app_commands.Choice(name="❌ Derrota",  value="derrota"),
        app_commands.Choice(name="🤝 Empate",   value="empate"),
    ])
    async def resultado(
        self,
        interaction: discord.Interaction,
        adversario: str,
        resultado: app_commands.Choice[str],
        placar: str = "",
    ):
        amistosos  = ler("amistosos")
        resultados = ler("resultados")
        perfis     = ler("perfis")

        # Encontra o amistoso correspondente (mais recente com esse adversário)
        amistoso_idx = None
        for i in range(len(amistosos) - 1, -1, -1):
            if adversario.lower() in amistosos[i]["adversario"].lower():
                amistoso_idx = i
                break

        emoji_resultado = {"vitoria": "✅ Vitória", "derrota": "❌ Derrota", "empate": "🤝 Empate"}[resultado.value]

        # Atualiza o amistoso no histórico
        if amistoso_idx is not None:
            amistosos[amistoso_idx]["resultado"] = emoji_resultado
            amistosos[amistoso_idx]["placar"]    = placar
            salvar("amistosos", amistosos)

            # Atualiza perfil dos jogadores confirmados
            confirmados = amistosos[amistoso_idx].get("confirmados", [])
            for mid in confirmados:
                sid = str(mid)
                if sid not in perfis:
                    perfis[sid] = {"nome": str(mid), "amistosos": 0, "vitorias": 0, "derrotas": 0}
                perfis[sid]["amistosos"] += 1
                if resultado.value == "vitoria":
                    perfis[sid]["vitorias"] += 1
                elif resultado.value == "derrota":
                    perfis[sid]["derrotas"] += 1
            salvar("perfis", perfis)

        # Salva no histórico geral de resultados
        resultados_lista = resultados if isinstance(resultados, list) else []
        resultados_lista.append({
            "adversario": adversario,
            "resultado":  resultado.value,
            "placar":     placar,
            "data":       agora_str(),
            "registrado_por": interaction.user.display_name,
        })
        salvar("resultados", resultados_lista)

        # Embed de confirmação
        cores = {"vitoria": 0x57F287, "derrota": 0xED4245, "empate": 0xFEE75C}
        embed = discord.Embed(
            title=f"{emoji_resultado}  TryHarders vs {adversario}",
            color=cores[resultado.value],
        )
        if placar:
            embed.add_field(name="⚽  Placar", value=f"**{placar}**", inline=True)
        embed.add_field(name="📅  Data", value=agora_str(), inline=True)
        embed.set_footer(text=f"Registrado por {interaction.user.display_name}")

        canal = self.bot.get_channel(AMISTOSOS_CHANNEL_ID)
        if canal:
            await canal.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Resultado registrado: **{emoji_resultado}** vs {adversario}{' — ' + placar if placar else ''}",
            ephemeral=True
        )
        print(f"[RESULTADO] ✅ {resultado.value} vs {adversario} registrado por {interaction.user}")

    @resultado.error
    async def resultado_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem registrar resultados.", ephemeral=True
            )

    # ── /ranking ──────────────────────────────────────────────────────────────
    @app_commands.command(name="ranking", description="Placar acumulado de vitórias do time.")
    async def ranking(self, interaction: discord.Interaction):
        resultados = ler("resultados")
        if isinstance(resultados, dict):
            resultados = []

        total     = len(resultados)
        vitorias  = sum(1 for r in resultados if r["resultado"] == "vitoria")
        derrotas  = sum(1 for r in resultados if r["resultado"] == "derrota")
        empates   = sum(1 for r in resultados if r["resultado"] == "empate")
        winrate   = f"{round((vitorias / total) * 100)}%" if total > 0 else "—"

        embed = discord.Embed(
            title="🏆  Placar TryHarders RL",
            color=0xD4A843,
        )
        embed.add_field(name="\u200b", value="```╔══════════  📊  GERAL  ══════════╗```", inline=False)
        embed.add_field(name="🎮  Total",    value=f"`{total}`",    inline=True)
        embed.add_field(name="✅  Vitórias", value=f"`{vitorias}`", inline=True)
        embed.add_field(name="❌  Derrotas", value=f"`{derrotas}`", inline=True)
        embed.add_field(name="🤝  Empates",  value=f"`{empates}`",  inline=True)
        embed.add_field(name="📊  Winrate",  value=f"`{winrate}`",  inline=True)

        # Últimos 5 resultados
        if resultados:
            embed.add_field(name="\u200b", value="```╔══════════  🕐  ÚLTIMOS JOGOS  ══════════╗```", inline=False)
            for r in resultados[-5:][::-1]:
                emoji = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}[r["resultado"]]
                placar = f" {r['placar']}" if r.get("placar") else ""
                embed.add_field(
                    name=f"{emoji}  vs {r['adversario']}{placar}",
                    value=f"📅 {r['data']}",
                    inline=False,
                )

        embed.set_footer(text=f"TryHarders RL • {agora_str()}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Resultados(bot))
