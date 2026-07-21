import asyncio
import io
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

from cogs.players import JOGADORES_CHANNEL_ID, _esta_oculto
from cogs.atividade import _ler as ler_atividade, limites_atuais

# ─────────────────────────────────────────────
#  Cog: Gráfico de Novatos da Semana
#  Arquivo: cogs/grafico_jogadores.py
#
#  Manda (e mantém atualizada) uma 2ª mensagem no mesmo canal da lista de
#  jogadores, sempre LOGO ABAIXO dela — um gráfico mostrando quantas
#  pessoas entraram no servidor nos últimos 7 dias e quantas dessas já
#  batem a meta de atividade (mesma regra do cogs/atividade.py: mais de
#  10 mensagens OU mais de 15 min em call).
# ─────────────────────────────────────────────

TITULO_EMBED = "📈 Novatos da Semana"


class GraficoJogadores(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id = None
        self.atualizar_grafico.start()

    def cog_unload(self):
        self.atualizar_grafico.cancel()

    @tasks.loop(minutes=15)
    async def atualizar_grafico(self):
        await self.bot.wait_until_ready()
        if not MATPLOTLIB_OK:
            return
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        if channel is None:
            print(f"[GRAFICO] ⚠️  Canal {JOGADORES_CHANNEL_ID} não encontrado.")
            return
        try:
            await self._editar_ou_criar(channel)
        except Exception as e:
            print(f"[GRAFICO] ⚠️ Erro ao atualizar gráfico: {e}")

    @atualizar_grafico.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()

    # ── Coleta os dados da última semana ─────────────────────────
    def _dados_semana(self, guild: discord.Guild):
        agora = datetime.now(timezone.utc)
        limite = agora - timedelta(days=7)

        novatos = [
            m for m in guild.members
            if not m.bot and m.joined_at is not None and m.joined_at >= limite and not _esta_oculto(m)
        ]

        atividade_dados = ler_atividade()
        mensagens_minimas, segundos_call_minimo = limites_atuais()
        ativos = 0
        for m in novatos:
            registro = atividade_dados.get(str(m.id))
            if not registro:
                continue
            bateu_msgs = registro.get("mensagens", 0) > mensagens_minimas
            bateu_call = registro.get("voz_segundos", 0) > segundos_call_minimo
            if bateu_msgs or bateu_call:
                ativos += 1

        return novatos, ativos

    # ── Gera a imagem (barra + pizza) ────────────────────────────
    def _gerar_grafico(self, total: int, ativos: int, guild_name: str) -> io.BytesIO:
        inativos = total - ativos

        plt.rcParams.update({
            "figure.facecolor": "#2b2d31",
            "axes.facecolor": "#2b2d31",
            "savefig.facecolor": "#2b2d31",
            "text.color": "#ffffff",
            "axes.edgecolor": "#ffffff",
            "axes.labelcolor": "#ffffff",
            "xtick.color": "#ffffff",
            "ytick.color": "#ffffff",
            "font.size": 11,
        })

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.2))

        # ── Barra: total de entradas na semana ──
        ax1.bar(["Novos jogadores"], [total], color="#D4A843", width=0.5)
        ax1.set_ylim(0, max(total, 1) + 1)
        ax1.set_title("Entradas na última semana", fontsize=12, weight="bold")
        ax1.text(0, total + max(total, 1) * 0.05, str(total), ha="center", fontweight="bold", fontsize=13)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)

        # ── Pizza: % ativos entre os novatos ──
        ax2.set_title("% Ativos entre os novatos", fontsize=12, weight="bold")
        if total > 0:
            valores = [ativos, inativos]
            labels = [f"Ativos ({ativos})", f"Inativos ({inativos})"]
            cores = ["#57F287", "#ED4245"]
            # remove fatias com valor 0 pra não quebrar o gráfico
            pares = [(v, l, c) for v, l, c in zip(valores, labels, cores) if v > 0]
            if pares:
                valores, labels, cores = zip(*pares)
                ax2.pie(
                    valores, labels=labels, autopct="%1.0f%%",
                    colors=cores, startangle=90,
                    textprops={"color": "#ffffff", "weight": "bold"},
                )
            else:
                ax2.text(0.5, 0.5, "Sem dados", ha="center", va="center")
                ax2.axis("off")
        else:
            ax2.text(0.5, 0.5, "Ninguém entrou\nnessa semana", ha="center", va="center", fontsize=12)
            ax2.axis("off")

        fig.suptitle(f"{guild_name} — Últimos 7 dias", fontsize=13, weight="bold", color="#D4A843")
        fig.tight_layout(rect=[0, 0, 1, 0.93])

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=150)
        plt.close(fig)
        buffer.seek(0)
        return buffer

    # ── Monta o embed + imagem e edita/cria a mensagem ───────────
    async def _editar_ou_criar(self, channel: discord.TextChannel):
        guild = channel.guild
        novatos, ativos = self._dados_semana(guild)
        total = len(novatos)
        pct = (ativos / total * 100) if total else 0

        buffer = await asyncio.to_thread(self._gerar_grafico, total, ativos, guild.name)
        arquivo = discord.File(buffer, filename="grafico_jogadores.png")

        embed = discord.Embed(
            title=TITULO_EMBED,
            description=(
                f"**{total}** jogador(es) entraram nos últimos 7 dias.\n"
                f"**{ativos}** já são considerados ativos — **{pct:.0f}%** dos novatos."
            ),
            color=0xFF5A1F,
        )
        embed.set_image(url="attachment://grafico_jogadores.png")
        embed.set_footer(text="Atualiza a cada 15 min")
        embed.timestamp = discord.utils.utcnow()

        if self.message_id:
            try:
                msg = await channel.fetch_message(self.message_id)
                await msg.edit(embed=embed, attachments=[arquivo])
                print("[GRAFICO] 🔄 Gráfico atualizado.")
                return
            except discord.NotFound:
                self.message_id = None

        async for msg in channel.history(limit=30):
            if msg.author == self.bot.user and msg.embeds and msg.embeds[0].title == TITULO_EMBED:
                self.message_id = msg.id
                await msg.edit(embed=embed, attachments=[arquivo])
                return

        nova = await channel.send(embed=embed, file=arquivo)
        self.message_id = nova.id
        print(f"[GRAFICO] ✅ Gráfico criado no canal #{channel.name}.")

    # ── Comando manual pra forçar atualização ────────────────────
    @commands.command(name="atualizargrafico")
    @commands.has_permissions(administrator=True)
    async def forcar_atualizacao(self, ctx: commands.Context):
        await ctx.message.delete()
        if not MATPLOTLIB_OK:
            await ctx.send("❌ `matplotlib` não está instalado no servidor do bot. Rode `pip install matplotlib`.", delete_after=8)
            return
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        await self._editar_ou_criar(channel)
        await ctx.send("✅ Gráfico atualizado!", delete_after=4)

    @forcar_atualizacao.error
    async def forcar_atualizacao_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    if not MATPLOTLIB_OK:
        print("[GRAFICO] ❌ matplotlib não está instalado — rode `pip install matplotlib` (ou `pip install -r requirements.txt`). O gráfico de novatos não vai funcionar até isso ser resolvido.")
    await bot.add_cog(GraficoJogadores(bot))
