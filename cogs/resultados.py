import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str
import asyncio

# ─────────────────────────────────────────────
#  Cog: Resultados
#  Arquivo: cogs/resultados.py
#  /resultado — registra resultado, salva transcrição,
#               DM nos jogadores e deleta canal
#  /ranking   — placar geral acumulado
# ─────────────────────────────────────────────

ADMIN_ROLE_ID        = 1511894837790769204
AMISTOSOS_CHANNEL_ID = 1514778555970621531

FRASES = {
    "vitoria": [
        "Vocês foram incríveis! Resultado merecido. 🚀",
        "Que jogo! A TryHarders mostrou do que é feita. 🔥",
        "Vitória conquistada com muita garra! Parabéns a todos. 🏆",
    ],
    "derrota": [
        "Nem toda batalha é vencida, mas o time deu tudo. Cabeça erguida! 💪",
        "Derrota faz parte. A TryHarders vai voltar mais forte. 🔄",
        "Obrigado por ter jogado. Cada jogo é aprendizado! 📈",
    ],
    "empate": [
        "Jogo equilibrado! A TryHarders segurou bem. ⚖️",
        "Empate justo. Time mostrou consistência! 👊",
    ],
}

import random


async def gerar_transcricao(canal: discord.TextChannel) -> str:
    """Gera uma transcrição simples em texto do canal."""
    linhas = [f"📄 Transcrição — #{canal.name}\n{'─'*40}\n"]
    async for msg in canal.history(limit=500, oldest_first=True):
        if msg.author.bot and not msg.embeds:
            continue
        hora = msg.created_at.strftime("%d/%m %H:%M")
        if msg.embeds:
            for e in msg.embeds:
                titulo = e.title or "Embed"
                linhas.append(f"[{hora}] 🤖 {msg.author.display_name}: [{titulo}]")
        else:
            linhas.append(f"[{hora}] {msg.author.display_name}: {msg.content}")
    return "\n".join(linhas)


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
        app_commands.Choice(name="✅ Vitória", value="vitoria"),
        app_commands.Choice(name="❌ Derrota", value="derrota"),
        app_commands.Choice(name="🤝 Empate",  value="empate"),
    ])
    async def resultado(
        self,
        interaction: discord.Interaction,
        adversario: str,
        resultado: app_commands.Choice[str],
        placar: str = "",
    ):
        await interaction.response.defer(ephemeral=True)

        amistosos  = ler("amistosos")
        resultados = ler("resultados")
        perfis     = ler("perfis")

        emoji_resultado = {"vitoria": "✅ Vitória", "derrota": "❌ Derrota", "empate": "🤝 Empate"}[resultado.value]
        cores           = {"vitoria": 0x57F287, "derrota": 0xED4245, "empate": 0xFEE75C}
        frase           = random.choice(FRASES[resultado.value])

        # Encontra o amistoso mais recente com esse adversário
        amistoso_idx  = None
        canal_amistoso = None
        confirmados_ids = []

        for i in range(len(amistosos) - 1, -1, -1):
            if adversario.lower() in amistosos[i]["adversario"].lower():
                amistoso_idx    = i
                confirmados_ids = amistosos[i].get("confirmados", [])
                canal_id        = amistosos[i].get("canal_id")
                if canal_id:
                    canal_amistoso = self.bot.get_channel(canal_id)
                break

        # ── Gera transcrição antes de deletar o canal ──────────────────────
        transcricao_texto = None
        transcricao_arquivo = None

        if canal_amistoso:
            try:
                transcricao_texto   = await gerar_transcricao(canal_amistoso)
                nome_arquivo        = f"transcricao-amistoso-{adversario.lower().replace(' ', '-')}.txt"
                transcricao_arquivo = nome_arquivo
                with open(nome_arquivo, "w", encoding="utf-8") as f:
                    f.write(transcricao_texto)
            except Exception as e:
                print(f"[RESULTADO] ⚠️ Erro ao gerar transcrição: {e}")

        # ── Atualiza histórico e perfis ────────────────────────────────────
        if amistoso_idx is not None:
            amistosos[amistoso_idx]["resultado"] = emoji_resultado
            amistosos[amistoso_idx]["placar"]    = placar
            salvar("amistosos", amistosos)

            for mid in confirmados_ids:
                sid = str(mid)
                if sid not in perfis:
                    perfis[sid] = {"nome": str(mid), "amistosos": 0, "vitorias": 0, "derrotas": 0}
                perfis[sid]["amistosos"] += 1
                if resultado.value == "vitoria":
                    perfis[sid]["vitorias"] += 1
                elif resultado.value == "derrota":
                    perfis[sid]["derrotas"] += 1
            salvar("perfis", perfis)

        resultados_lista = resultados if isinstance(resultados, list) else []
        resultados_lista.append({
            "adversario":     adversario,
            "resultado":      resultado.value,
            "placar":         placar,
            "data":           agora_str(),
            "registrado_por": interaction.user.display_name,
        })
        salvar("resultados", resultados_lista)

        # ── DM para cada jogador confirmado ────────────────────────────────
        placar_texto = f" — **{placar}**" if placar else ""
        dm_enviadas  = 0
        dm_falhas    = 0

        for mid in confirmados_ids:
            membro = interaction.guild.get_member(mid)
            if membro is None:
                continue
            try:
                embed_dm = discord.Embed(
                    title=f"{emoji_resultado}  TryHarders vs {adversario}",
                    description=frase,
                    color=cores[resultado.value],
                )
                if placar:
                    embed_dm.add_field(name="⚽  Placar final", value=f"**{placar}**", inline=True)
                embed_dm.add_field(name="📅  Data", value=agora_str(), inline=True)

                if transcricao_arquivo:
                    embed_dm.add_field(
                        name="📄  Transcrição do canal",
                        value="Se desejar ver a transcrição completa do canal do amistoso, ela está anexada abaixo.",
                        inline=False,
                    )

                embed_dm.set_footer(text="TryHarders RL 🚀")

                dm = await membro.create_dm()
                if transcricao_arquivo:
                    await dm.send(
                        embed=embed_dm,
                        file=discord.File(transcricao_arquivo, filename=transcricao_arquivo)
                    )
                else:
                    await dm.send(embed=embed_dm)

                dm_enviadas += 1
            except discord.Forbidden:
                dm_falhas += 1
                print(f"[RESULTADO] ⚠️ Não foi possível enviar DM para {membro}.")

        # ── Embed público no canal de amistosos ────────────────────────────
        embed_pub = discord.Embed(
            title=f"{emoji_resultado}  TryHarders vs {adversario}{placar_texto}",
            description=frase,
            color=cores[resultado.value],
        )
        embed_pub.add_field(name="📅  Data", value=agora_str(), inline=True)
        if dm_enviadas:
            embed_pub.add_field(
                name="📬  DMs enviadas",
                value=f"`{dm_enviadas}` jogador(es) notificados",
                inline=True
            )
        embed_pub.set_footer(text=f"Registrado por {interaction.user.display_name}")

        canal_pub = self.bot.get_channel(AMISTOSOS_CHANNEL_ID)
        if canal_pub:
            await canal_pub.send(embed=embed_pub)

        # ── Deleta o canal do amistoso ─────────────────────────────────────
        if canal_amistoso:
            await asyncio.sleep(3)
            try:
                await canal_amistoso.delete(reason=f"Amistoso vs {adversario} encerrado — resultado registrado.")
                print(f"[RESULTADO] 🗑️ Canal {canal_amistoso.name} deletado.")
            except Exception as e:
                print(f"[RESULTADO] ⚠️ Erro ao deletar canal: {e}")

        # Limpa arquivo de transcrição temporário
        if transcricao_arquivo:
            try:
                import os
                os.remove(transcricao_arquivo)
            except Exception:
                pass

        await interaction.followup.send(
            f"✅ Resultado registrado! {emoji_resultado} vs **{adversario}**{placar_texto}\n"
            f"📬 DMs enviadas: `{dm_enviadas}` | ❌ Falhas: `{dm_falhas}`",
            ephemeral=True
        )
        print(f"[RESULTADO] ✅ {resultado.value} vs {adversario} | DMs: {dm_enviadas}/{len(confirmados_ids)}")

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

        total    = len(resultados)
        vitorias = sum(1 for r in resultados if r["resultado"] == "vitoria")
        derrotas = sum(1 for r in resultados if r["resultado"] == "derrota")
        empates  = sum(1 for r in resultados if r["resultado"] == "empate")
        winrate  = f"{round((vitorias / total) * 100)}%" if total > 0 else "—"

        embed = discord.Embed(title="🏆  Placar TryHarders RL", color=0xD4A843)
        embed.add_field(name="\u200b", value="```╔══════════  📊  GERAL  ══════════╗```", inline=False)
        embed.add_field(name="🎮  Total",    value=f"`{total}`",    inline=True)
        embed.add_field(name="✅  Vitórias", value=f"`{vitorias}`", inline=True)
        embed.add_field(name="❌  Derrotas", value=f"`{derrotas}`", inline=True)
        embed.add_field(name="🤝  Empates",  value=f"`{empates}`",  inline=True)
        embed.add_field(name="📊  Winrate",  value=f"`{winrate}`",  inline=True)

        if resultados:
            embed.add_field(name="\u200b", value="```╔══════════  🕐  ÚLTIMOS JOGOS  ══════════╗```", inline=False)
            for r in resultados[-5:][::-1]:
                emoji  = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}[r["resultado"]]
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
