import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

from cogs.backup import ler, salvar

# ─────────────────────────────────────────────
#  Cog: Medalhas Desbloqueáveis
#  Arquivo: cogs/medalhas.py
#
#  Sistema de conquistas (badges) ligado ao perfil de cada jogador
#  (data/perfis.json — o mesmo arquivo usado pelo /perfil em stats.py).
#
#  Toda vez que os amistosos/vitórias de alguém mudam (resultados.py) ou
#  que a pessoa manda uma mensagem, o bot confere se alguma medalha nova
#  foi desbloqueada e, se sim, anuncia no canal de jogadores.
#
#  Comando: /medalhas [membro] — mostra as medalhas conquistadas e as
#  que ainda faltam.
# ─────────────────────────────────────────────

CANAL_ANUNCIO_ID = 1514775408124367149  # canal de jogadores (mesmo de cogs/players.py)


def _criterio(campo: str, minimo: int):
    """Fábrica de critério simples: desbloqueia quando contexto[campo] >= minimo."""
    def checar(contexto: dict) -> bool:
        return contexto.get(campo, 0) >= minimo
    return checar


# Lista de medalhas disponíveis. Pra adicionar uma nova, basta incluir mais
# um dicionário aqui — o resto do sistema (checagem, anúncio, /medalhas)
# já funciona automaticamente pra ela.
MEDALHAS = [
    {"id": "estreante",         "emoji": "🎮",  "nome": "Estreante",            "descricao": "Dispute seu 1º amistoso.",           "criterio": _criterio("amistosos", 1)},
    {"id": "veterano",          "emoji": "🥈",  "nome": "Veterano",             "descricao": "Dispute 25 amistosos.",               "criterio": _criterio("amistosos", 25)},
    {"id": "lenda_amistosos",   "emoji": "🏆",  "nome": "Lenda dos Amistosos",  "descricao": "Dispute 100 amistosos.",              "criterio": _criterio("amistosos", 100)},
    {"id": "vencedor",          "emoji": "🥇",  "nome": "Vencedor",             "descricao": "Vença 10 amistosos.",                 "criterio": _criterio("vitorias", 10)},
    {"id": "imparavel",         "emoji": "👑",  "nome": "Imparável",            "descricao": "Vença 50 amistosos.",                 "criterio": _criterio("vitorias", 50)},
    {"id": "tagarela",          "emoji": "💬",  "nome": "Tagarela",             "descricao": "Mande 500 mensagens no servidor.",    "criterio": _criterio("mensagens_totais", 500)},
    {"id": "lenda_do_chat",     "emoji": "📢",  "nome": "Lenda do Chat",        "descricao": "Mande 2.000 mensagens no servidor.",  "criterio": _criterio("mensagens_totais", 2000)},
    {"id": "membro_fiel",       "emoji": "⏳",  "nome": "Membro Fiel",          "descricao": "Fique 6 meses no servidor.",          "criterio": _criterio("dias_no_servidor", 180)},
    {"id": "veterano_do_clube", "emoji": "🏛️", "nome": "Veterano do Clube",    "descricao": "Fique 1 ano no servidor.",            "criterio": _criterio("dias_no_servidor", 365)},
]
MEDALHAS_POR_ID = {m["id"]: m for m in MEDALHAS}


def _garantir_perfil_completo(perfis: dict, sid: str, nome: str) -> dict:
    """Garante que o perfil existe e tem todos os campos usados pelas medalhas
    (perfis criados antes desse sistema existir não tinham esses campos)."""
    if sid not in perfis:
        perfis[sid] = {"nome": nome, "amistosos": 0, "vitorias": 0, "derrotas": 0}
    dados = perfis[sid]
    dados.setdefault("amistosos", 0)
    dados.setdefault("vitorias", 0)
    dados.setdefault("derrotas", 0)
    dados.setdefault("mensagens_totais", 0)
    dados.setdefault("medalhas", [])
    return dados


def _montar_contexto(dados: dict, membro) -> dict:
    dias_no_servidor = 0
    if isinstance(membro, discord.Member) and membro.joined_at:
        dias_no_servidor = (datetime.now(timezone.utc) - membro.joined_at).days
    return {
        "amistosos":        dados.get("amistosos", 0),
        "vitorias":         dados.get("vitorias", 0),
        "derrotas":         dados.get("derrotas", 0),
        "mensagens_totais": dados.get("mensagens_totais", 0),
        "dias_no_servidor": dias_no_servidor,
    }


class Medalhas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Confere e concede medalhas novas pra um membro, anunciando as novas ──
    # Chamado automaticamente aqui (on_message) e também de fora (ex:
    # cogs/resultados.py, depois de atualizar amistosos/vitórias no perfil).
    async def verificar_membro(self, membro, guild: discord.Guild = None) -> list:
        perfis = ler("perfis")
        sid = str(membro.id)
        dados = _garantir_perfil_completo(perfis, sid, getattr(membro, "display_name", str(membro)))
        contexto = _montar_contexto(dados, membro)

        ja_tem = set(dados["medalhas"])
        novas = []
        for medalha in MEDALHAS:
            if medalha["id"] in ja_tem:
                continue
            try:
                desbloqueou = medalha["criterio"](contexto)
            except Exception as e:
                print(f"[MEDALHAS] ⚠️ Erro ao checar critério de '{medalha['id']}': {e}")
                continue
            if desbloqueou:
                dados["medalhas"].append(medalha["id"])
                novas.append(medalha)

        salvar("perfis", perfis)

        if novas:
            await self._anunciar_novas_medalhas(membro, novas)
        return novas

    async def _anunciar_novas_medalhas(self, membro, novas: list):
        canal = self.bot.get_channel(CANAL_ANUNCIO_ID)
        if canal is None:
            print(f"[MEDALHAS] ⚠️ Canal {CANAL_ANUNCIO_ID} não encontrado.")
            return

        for medalha in novas:
            embed = discord.Embed(
                title="🎖️ Nova Medalha Desbloqueada!",
                description=(
                    f"{membro.mention} desbloqueou a medalha "
                    f"{medalha['emoji']} **{medalha['nome']}**!\n"
                    f"_{medalha['descricao']}_"
                ),
                color=0xD4A843,
                timestamp=datetime.now(timezone.utc),
            )
            avatar = getattr(membro, "display_avatar", None)
            if avatar:
                embed.set_thumbnail(url=avatar.url)
            try:
                msg = await canal.send(embed=embed)
                await msg.delete(delay=300)
            except discord.HTTPException as e:
                print(f"[MEDALHAS] ⚠️ Erro ao anunciar medalha: {e}")

        print(f"[MEDALHAS] 🎖️ {membro} desbloqueou: {', '.join(m['id'] for m in novas)}")

    # ── Mensagens contam pro contador lifetime usado pelas medalhas de chat ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        perfis = ler("perfis")
        sid = str(message.author.id)
        dados = _garantir_perfil_completo(perfis, sid, message.author.display_name)
        dados["mensagens_totais"] += 1
        salvar("perfis", perfis)

        await self.verificar_membro(message.author, message.guild)

    # ── /medalhas — mostra as medalhas conquistadas e as que faltam ─────────
    @app_commands.command(name="medalhas", description="Veja as medalhas de um jogador.")
    @app_commands.describe(membro="Jogador que deseja consultar (deixe vazio para ver as suas)")
    async def medalhas_cmd(self, interaction: discord.Interaction, membro: discord.Member = None):
        membro = membro or interaction.user
        perfis = ler("perfis")
        sid = str(membro.id)
        dados = _garantir_perfil_completo(perfis, sid, membro.display_name)
        salvar("perfis", perfis)

        conquistadas_ids = set(dados.get("medalhas", []))

        conquistadas_txt = "\n".join(
            f"{m['emoji']} **{m['nome']}** — _{m['descricao']}_"
            for m in MEDALHAS if m["id"] in conquistadas_ids
        ) or "_Nenhuma medalha conquistada ainda._"

        faltando_txt = "\n".join(
            f"🔒 **{m['nome']}** — _{m['descricao']}_"
            for m in MEDALHAS if m["id"] not in conquistadas_ids
        ) or "_Todas as medalhas já foram conquistadas!_"

        embed = discord.Embed(
            title=f"🎖️ Medalhas de {membro.display_name}",
            color=0xD4A843,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name=f"✅ Conquistadas ({len(conquistadas_ids)}/{len(MEDALHAS)})", value=conquistadas_txt, inline=False)
        embed.add_field(name="🔒 Bloqueadas", value=faltando_txt, inline=False)
        embed.set_footer(text="Medalhas são desbloqueadas automaticamente conforme você joga e interage no servidor.")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Medalhas(bot))
