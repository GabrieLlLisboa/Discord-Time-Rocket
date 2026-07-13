import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str

# ─────────────────────────────────────────────
#  Cog: Estatísticas
#  Arquivo: cogs/stats.py
#  /perfil @membro — /historico
# ─────────────────────────────────────────────

RANKS_IDS = {
    1514772134327488642: ("🌌", "Super Sonic Legend"),
    1513343857125752992: ("👑", "Grand Champion"),
    1512304793534861313: ("🏅", "Champion"),
    1512305401075466320: ("💎", "Diamante"),
    1512305547544625273: ("🪙", "Platina"),
    1512571913849933956: ("🥇", "Ouro"),
    1513356584946896946: ("📋", "Coach"),
    1513240072139309317: ("🎬", "Editor de vídeo"),
    1511894837790769204: ("🥈", "Sub-Dono"),
}
ADMIN_ROLE_ID = 1511894837790769204


def obter_rank(member: discord.Member) -> str:
    for role in member.roles:
        if role.id in RANKS_IDS:
            emoji, nome = RANKS_IDS[role.id]
            return f"{emoji} {nome}"
    return "Sem cargo"


def garantir_perfil(member_id: int, member_name: str):
    perfis = ler("perfis")
    sid = str(member_id)
    if sid not in perfis:
        perfis[sid] = {
            "nome":              member_name,
            "amistosos":         0,
            "vitorias":          0,
            "derrotas":          0,
        }
        salvar("perfis", perfis)
    return perfis


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /perfil ───────────────────────────────────────────────────────────────
    @app_commands.command(name="perfil", description="Veja o perfil de um jogador.")
    @app_commands.describe(membro="Jogador que deseja consultar (deixe vazio para ver o seu)")
    async def perfil(self, interaction: discord.Interaction, membro: discord.Member = None):
        membro = membro or interaction.user
        perfis = garantir_perfil(membro.id, membro.display_name)
        dados  = perfis.get(str(membro.id), {})

        rank        = obter_rank(membro)
        amistosos   = dados.get("amistosos", 0)
        vitorias    = dados.get("vitorias",  0)
        derrotas    = dados.get("derrotas",  0)
        entrou_em   = discord.utils.format_dt(membro.joined_at, style="D") if membro.joined_at else "Desconhecido"
        conta_criada = discord.utils.format_dt(membro.created_at, style="D")

        winrate = f"{round((vitorias / amistosos) * 100)}%" if amistosos > 0 else "—"

        embed = discord.Embed(
            title=f"👤  {membro.display_name}",
            color=0xD4A843,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="\u200b", value="```╔══════════  📋  PERFIL  ══════════╗```", inline=False)
        embed.add_field(name="🏷️  Cargo",          value=rank,         inline=True)
        embed.add_field(name="📅  Entrou em",       value=entrou_em,    inline=True)
        embed.add_field(name="🗓️  Conta criada",    value=conta_criada, inline=True)
        embed.add_field(name="\u200b", value="```╔══════════  ⚽  AMISTOSOS  ══════════╗```", inline=False)
        embed.add_field(name="🎮  Disputados", value=f"`{amistosos}`", inline=True)
        embed.add_field(name="✅  Vitórias",   value=f"`{vitorias}`",  inline=True)
        embed.add_field(name="❌  Derrotas",   value=f"`{derrotas}`",  inline=True)
        embed.add_field(name="📊  Winrate",    value=f"`{winrate}`",   inline=True)
        embed.set_footer(text=f"TryHarders RL • {agora_str()}")

        await interaction.response.send_message(embed=embed)

    # ── /historico ────────────────────────────────────────────────────────────
    @app_commands.command(name="historico", description="Veja o histórico de amistosos registrados.")
    async def historico(self, interaction: discord.Interaction):
        amistosos = ler("amistosos")

        if not amistosos:
            await interaction.response.send_message(
                "📭 Nenhum amistoso registrado ainda.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋  Histórico de Amistosos",
            color=0xD4A843,
        )

        for a in amistosos[-10:][::-1]:  # últimos 10, mais recente primeiro
            resultado = a.get("resultado", "⏳ Aguardando")
            placar    = a.get("placar", "")
            valor = (
                f"📅 {a['data']}  |  {a['rank']}\n"
                f"{resultado}{' — ' + placar if placar else ''}"
            )
            embed.add_field(
                name=f"🆚  TryHarders vs {a['adversario']}",
                value=valor,
                inline=False,
            )

        embed.set_footer(text=f"Mostrando os últimos {min(len(amistosos), 10)} amistosos")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
