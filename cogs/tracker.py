import discord
from discord.ext import commands
import httpx
import os
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Tracker (Rank Rocket League)
#  Arquivo: cogs/tracker.py
#  Comandos: !tracker
#  Botão → Modal (nick) → busca rank na Tracker Network
#  e envia o resultado em privado (ephemeral) pro jogador.
# ─────────────────────────────────────────────

TRN_API_KEY = os.getenv("TRN_API_KEY", "")
TRN_BASE_URL = "https://api.tracker.gg/api/v2/rocket-league/standard/profile"

PLATAFORMAS_VALIDAS = {
    "epic":  "epic",
    "steam": "steam",
    "psn":   "psn",
    "xbl":   "xbl",
    "xbox":  "xbl",
    "ps":    "psn",
}

# Nome do segmento na API da Tracker Network → nome bonito pra exibir
MODOS = {
    "Ranked Duel 1v1":     ("🥇", "1v1 — Duel"),
    "Ranked Doubles 2v2":  ("🥈", "2v2 — Doubles"),
    "Ranked Standard 3v3": ("🥉", "3v3 — Standard"),
}


def _formatar_tempo_conta(timestamp_iso: str) -> str:
    """Recebe uma data ISO e retorna algo tipo '2 anos e 3 meses'."""
    try:
        criado_em = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "Indisponível"

    agora = datetime.now(timezone.utc)
    dias = (agora - criado_em).days
    anos, resto = divmod(dias, 365)
    meses = resto // 30

    partes = []
    if anos:
        partes.append(f"{anos} ano{'s' if anos != 1 else ''}")
    if meses:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if not partes:
        partes.append(f"{dias} dia{'s' if dias != 1 else ''}")

    return " e ".join(partes)


async def buscar_rank_rl(nick: str, plataforma: str = "epic") -> dict:
    """
    Busca o perfil do jogador na Tracker Network.
    Retorna um dict com: erro (str|None), ranks (dict modo -> info), tempo_conta (str).

    Documentação: https://tracker.gg/developers
    Requer TRN_API_KEY configurada no .env.
    """
    if not TRN_API_KEY:
        return {"erro": "⚠️ A `TRN_API_KEY` não foi configurada no `.env` do bot."}

    plataforma = PLATAFORMAS_VALIDAS.get(plataforma.lower().strip(), "epic")
    url = f"{TRN_BASE_URL}/{plataforma}/{nick}"
    headers = {
        "TRN-Api-Key": TRN_API_KEY,
        "User-Agent": "Mozilla/5.0 (compatible; IgnitionRLBot/1.0; +https://discord.com)",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError:
        return {"erro": "❌ Não consegui me conectar à Tracker Network. Tente novamente mais tarde."}

    if resp.status_code == 404:
        return {"erro": f"❌ Nenhum jogador encontrado com o nick **{nick}** na plataforma `{plataforma}`."}
    if resp.status_code == 401:
        return {"erro": "🔑 A `TRN_API_KEY` é inválida. Gere uma nova em tracker.gg/developers."}
    if resp.status_code == 403:
        return {
            "erro": (
                "🚫 A Tracker Network bloqueou essa requisição (status 403).\n"
                "Possíveis causas: app ainda pendente de aprovação no tracker.gg/developers, "
                "chave incorreta/expirada, ou bloqueio de IP do servidor onde o bot está rodando.\n"
                "Confira o status do seu app no painel da Tracker Network."
            )
        }
    if resp.status_code == 429:
        return {"erro": "⏳ Limite de requisições da API atingido. Tente novamente em alguns minutos."}
    if resp.status_code != 200:
        return {"erro": f"❌ Erro ao consultar a Tracker Network (status {resp.status_code})."}

    data = resp.json().get("data", {})

    # Tempo de conta (data de criação reportada pela plataforma)
    metadata = data.get("metadata", {})
    criado_em = metadata.get("dateCreated") or metadata.get("createdAt")
    tempo_conta = _formatar_tempo_conta(criado_em) if criado_em else "Indisponível"

    # Ranks por modo
    ranks = {}
    for segmento in data.get("segments", []):
        nome_segmento = segmento.get("metadata", {}).get("name", "")
        if nome_segmento not in MODOS:
            continue

        stats = segmento.get("stats", {})
        rank_info = stats.get("tier", {}).get("metadata", {})
        nome_rank = rank_info.get("name", "Sem rank")
        divisao = stats.get("division", {}).get("metadata", {}).get("name", "")
        mmr = stats.get("rating", {}).get("value")

        ranks[nome_segmento] = {
            "rank": f"{nome_rank} {divisao}".strip(),
            "mmr": int(mmr) if mmr is not None else None,
        }

    return {"erro": None, "ranks": ranks, "tempo_conta": tempo_conta, "nick": nick, "plataforma": plataforma}


# ── Modal: Buscar Rank ─────────────────────────────────────────────────────────
class TrackerModal(discord.ui.Modal, title="🔎 Buscar Rank — Rocket League"):
    nick = discord.ui.TextInput(
        label="Nick do jogador",
        placeholder="Ex: TryHarder#2847 (copie igual está no jogo)",
        max_length=64,
    )
    plataforma = discord.ui.TextInput(
        label="Plataforma (epic, steam, psn ou xbl)",
        placeholder="Deixe em branco para usar Epic Games (padrão)",
        required=False,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        nick = self.nick.value.strip()
        plataforma = self.plataforma.value.strip() or "epic"

        resultado = await buscar_rank_rl(nick, plataforma)

        if resultado.get("erro"):
            await interaction.followup.send(resultado["erro"], ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🚀  Rank de {resultado['nick']}",
            description=f"Plataforma: `{resultado['plataforma']}`",
            color=0xD4A843,
        )

        ranks = resultado["ranks"]
        if not ranks:
            embed.add_field(
                name="⚠️ Sem dados de rank",
                value="Não foi possível encontrar ranks competitivos para esse jogador.",
                inline=False,
            )
        else:
            for nome_segmento, (emoji, label) in MODOS.items():
                info = ranks.get(nome_segmento)
                if not info:
                    valor = "Sem dados"
                else:
                    valor = info["rank"]
                    if info["mmr"] is not None:
                        valor += f"  •  `{info['mmr']} MMR`"
                embed.add_field(name=f"{emoji}  {label}", value=valor, inline=False)

        embed.add_field(name="🗓️  Tempo de conta", value=resultado["tempo_conta"], inline=False)
        embed.set_footer(text="Ignition RL • Dados via Tracker Network")

        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"[TRACKER] ✅ Rank de '{nick}' consultado por {interaction.user}.")


# ── View: Botão que abre o Modal ───────────────────────────────────────────────
class TrackerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔎 Buscar Rank",
        style=discord.ButtonStyle.primary,
        custom_id="abrir_modal_tracker",
    )
    async def abrir_tracker(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrackerModal())


# ── Cog principal ──────────────────────────────────────────────────────────────
class Tracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="tracker")
    async def tracker(self, ctx: commands.Context):
        """Envia o painel de consulta de rank do Rocket League."""
        await ctx.message.delete()

        embed = discord.Embed(
            title="🚀  Consulta de Rank — Rocket League",
            description=(
                "Clique no botão abaixo e informe o **nick** do jogador.\n"
                "Você vai receber, em privado, o rank dele nos modos:\n\n"
                "🥇 **1v1** — Duel\n"
                "🥈 **2v2** — Doubles\n"
                "🥉 **3v3** — Standard\n"
                "🗓️ **Tempo de conta**\n\n"
                "_Sugestão: use o nick completo, igual aparece no jogo "
                "(ex: `TryHarder#2847` na Epic)._"
            ),
            color=0x2B2D31,
        )
        embed.set_footer(text="Apenas você verá o resultado da busca.")

        await ctx.send(embed=embed, view=TrackerView())
        print(f"[TRACKER] ✅ Painel de tracker enviado em #{ctx.channel.name} por {ctx.author}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tracker(bot))
