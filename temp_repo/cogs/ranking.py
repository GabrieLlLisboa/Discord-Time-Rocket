import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler
from cogs.players import CARGOS_RANK, RANK_IDS
from cogs.paginacao import paginar, PaginacaoView

# ─────────────────────────────────────────────
#  Cog: Ranking Interno
#  Arquivo: cogs/ranking.py
#
#  Ranking dos jogadores da TryHarders, montado a partir dos cargos de rank
#  do Discord (cogs/players.py) + estatísticas do perfil (data/perfis.json,
#  o mesmo arquivo usado por /perfil em cogs/stats.py). Não guarda nada
#  próprio — é só uma visão ordenável dos dados que já existem.
#
#  Critérios de ordenação (/ranking criterio:):
#    • Rank        — pelo cargo de rank atual (Super Sonic Legend no topo)
#    • Habilidade   — nota manual 0-100 definida via /perfil-editar (staff)
#    • Partidas     — total de amistosos disputados
#    • Desempenho   — winrate (vitórias / partidas)
# ─────────────────────────────────────────────

# índice 0 = rank mais alto (CARGOS_RANK já vem ordenado assim em players.py)
_ORDEM_RANK = {c["id"]: i for i, c in enumerate(CARGOS_RANK)}


def _posicao_rank(membro: discord.Member) -> tuple[int, str]:
    """(índice do rank pra ordenar — menor é melhor, nome pra exibir)."""
    for role in membro.roles:
        if role.id in _ORDEM_RANK:
            info = next(c for c in CARGOS_RANK if c["id"] == role.id)
            return _ORDEM_RANK[role.id], f"{info['emoji']} {info['nome']}"
    return len(CARGOS_RANK), "Sem rank"


class Ranking(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ranking", description="Veja o ranking interno da TryHarders.")
    @app_commands.describe(criterio="Como ordenar o ranking")
    @app_commands.choices(criterio=[
        app_commands.Choice(name="🏷️ Rank",       value="rank"),
        app_commands.Choice(name="📈 Habilidade",  value="habilidade"),
        app_commands.Choice(name="🎮 Partidas",    value="partidas"),
        app_commands.Choice(name="📊 Desempenho",  value="desempenho"),
    ])
    async def ranking_cmd(self, interaction: discord.Interaction, criterio: app_commands.Choice[str] = None):
        criterio_valor = criterio.value if criterio else "rank"
        criterio_label = criterio.name if criterio else "🏷️ Rank"

        await interaction.response.defer()

        perfis = ler("perfis")
        guild = interaction.guild

        linhas = []
        for membro in guild.members:
            if membro.bot:
                continue
            sid = str(membro.id)
            dados = perfis.get(sid, {})

            amistosos = dados.get("amistosos", 0)
            vitorias  = dados.get("vitorias", 0)
            habilidade = dados.get("habilidade")
            idx_rank, rank_nome = _posicao_rank(membro)
            winrate = (vitorias / amistosos) if amistosos > 0 else 0.0

            # só entra no ranking quem tem rank OU já tem alguma estatística —
            # evita poluir o ranking com quem nunca jogou nada e não tem cargo
            if idx_rank == len(CARGOS_RANK) and amistosos == 0 and habilidade is None:
                continue

            linhas.append({
                "membro": membro,
                "rank_idx": idx_rank,
                "rank_nome": rank_nome,
                "habilidade": habilidade,
                "partidas": amistosos,
                "vitorias": vitorias,
                "winrate": winrate,
            })

        if not linhas:
            await interaction.followup.send("📭 Ainda não há dados suficientes para montar o ranking.")
            return

        if criterio_valor == "rank":
            linhas.sort(key=lambda l: (l["rank_idx"], -l["partidas"]))
        elif criterio_valor == "habilidade":
            linhas = [l for l in linhas if l["habilidade"] is not None]
            linhas.sort(key=lambda l: -l["habilidade"])
        elif criterio_valor == "partidas":
            linhas.sort(key=lambda l: -l["partidas"])
        elif criterio_valor == "desempenho":
            linhas = [l for l in linhas if l["partidas"] > 0]
            linhas.sort(key=lambda l: (-l["winrate"], -l["partidas"]))

        if not linhas:
            await interaction.followup.send(
                "📭 Nenhum jogador tem dado suficiente para esse critério ainda."
            )
            return

        medalhas_pos = ["🥇", "🥈", "🥉"]

        def montar_pagina(pagina, total, fatia, offset):
            embed = discord.Embed(
                title=f"🏆 Ranking TryHarders RL — {criterio_label}",
                color=0xD4A843,
            )
            for i, l in enumerate(fatia):
                posicao = offset + i
                prefixo = medalhas_pos[posicao] if posicao < 3 else f"`#{posicao + 1}`"
                winrate_txt = f"{round(l['winrate'] * 100)}%" if l["partidas"] > 0 else "—"
                habilidade_txt = str(l["habilidade"]) if l["habilidade"] is not None else "—"
                embed.add_field(
                    name=f"{prefixo}  {l['membro'].display_name}",
                    value=(
                        f"{l['rank_nome']}  •  📈 `{habilidade_txt}`  •  "
                        f"🎮 `{l['partidas']}`  •  📊 `{winrate_txt}`"
                    ),
                    inline=False,
                )
            embed.set_footer(text=f"Página {pagina}/{total}  •  {len(linhas)} jogador(es) no ranking")
            return embed

        embeds = paginar(linhas, 10, montar_pagina)
        view = PaginacaoView(embeds) if len(embeds) > 1 else None
        await interaction.followup.send(embed=embeds[0], view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ranking(bot))
