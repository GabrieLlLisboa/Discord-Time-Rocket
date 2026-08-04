import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Usuário Mais Ativo (diário)
#  Arquivo: cogs/mais_ativo.py
#
#  Conta quantas mensagens cada pessoa manda por dia (fuso de Brasília) e,
#  assim que o dia vira, anuncia no canal de jogadores quem foi o usuário
#  mais ativo do dia anterior — considerando SÓ mensagens (call não conta).
# ─────────────────────────────────────────────

CANAL_RANKING_ID = 1514775408124367149  # canal de jogadores (mesmo de cogs/players.py)

BR_TZ = timezone(timedelta(hours=-3))

DATA_PATH = "data/atividade_diaria.json"           # {"YYYY-MM-DD": {"user_id": qtd_mensagens}}
CONTROLE_PATH = "data/atividade_diaria_controle.json"  # {"ultimo_dia_anunciado": "YYYY-MM-DD"}

DIAS_PARA_MANTER = 60  # não deixa o histórico crescer pra sempre


def _hoje_str() -> str:
    return datetime.now(BR_TZ).strftime("%Y-%m-%d")


def _ontem_str() -> str:
    return (datetime.now(BR_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def _ler_dados() -> dict:
    return ler_json(DATA_PATH, dict)


def _salvar_dados(dados: dict):
    salvar_json(DATA_PATH, dados)


def _ler_controle() -> dict:
    return ler_json(CONTROLE_PATH, dict)


def _salvar_controle(dados: dict):
    salvar_json(CONTROLE_PATH, dados)


class MaisAtivo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = _ler_dados()
        self.verificar_virada_dia.start()

    def cog_unload(self):
        self.verificar_virada_dia.cancel()

    # ── Conta mensagens do dia atual ─────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        dia = _hoje_str()
        registro_dia = self.dados.setdefault(dia, {})
        sid = str(message.author.id)
        registro_dia[sid] = registro_dia.get(sid, 0) + 1
        _salvar_dados(self.dados)

        # Poda dias antigos de vez em quando (não precisa ser toda mensagem,
        # mas fazer aqui é simples e barato o suficiente)
        if len(self.dados) > DIAS_PARA_MANTER:
            for antigo in sorted(self.dados.keys())[:-DIAS_PARA_MANTER]:
                del self.dados[antigo]
            _salvar_dados(self.dados)

    # ── Monta e manda o embed de ranking de um dia específico ───────────────
    async def _anunciar_mais_ativo(self, guild: discord.Guild, dia: str):
        registro_dia = self.dados.get(dia, {})
        if not registro_dia:
            print(f"[MAIS_ATIVO] ℹ️ Ninguém mandou mensagem em {dia}, nada pra anunciar.")
            return

        canal = self.bot.get_channel(CANAL_RANKING_ID)
        if canal is None:
            print(f"[MAIS_ATIVO] ⚠️ Canal {CANAL_RANKING_ID} não encontrado.")
            return

        ranking = sorted(registro_dia.items(), key=lambda par: par[1], reverse=True)
        top_id_str, top_qtd = ranking[0]

        top_membro = guild.get_member(int(top_id_str))
        if top_membro is None:
            try:
                top_membro = await self.bot.fetch_user(int(top_id_str))
            except discord.HTTPException:
                top_membro = None

        data_formatada = datetime.strptime(dia, "%Y-%m-%d").strftime("%d/%m/%Y")

        linhas = []
        for i, (uid_str, qtd) in enumerate(ranking[:5], start=1):
            membro = guild.get_member(int(uid_str))
            nome = membro.display_name if membro else f"<@{uid_str}>"
            medalha = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "▫️")
            linhas.append(f"{medalha} **{nome}** — `{qtd}` mensagens")

        embed = discord.Embed(
            title="💬 Usuário Mais Ativo do Dia",
            description=(
                f"No dia **{data_formatada}**, quem mais mandou mensagens foi "
                f"{top_membro.mention if top_membro else f'<@{top_id_str}>'} "
                f"com **{top_qtd}** mensagens! 🎉"
            ),
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc),
        )
        if len(ranking) > 1:
            embed.add_field(name="🏆 Top 5 do dia", value="\n".join(linhas), inline=False)
        if top_membro is not None:
            embed.set_thumbnail(url=top_membro.display_avatar.url)
        embed.set_footer(text="Considera apenas mensagens enviadas — tempo de call não conta aqui.")

        try:
            await canal.send(embed=embed)
            print(f"[MAIS_ATIVO] ✅ Anunciado usuário mais ativo de {dia}: {top_membro} ({top_qtd} msgs).")
        except discord.HTTPException as e:
            print(f"[MAIS_ATIVO] ⚠️ Erro ao anunciar usuário mais ativo: {e}")

    # ── Confere a cada minuto se o dia virou, pra anunciar o dia anterior ───
    @tasks.loop(minutes=1)
    async def verificar_virada_dia(self):
        await self.bot.wait_until_ready()
        ontem = _ontem_str()

        controle = _ler_controle()
        if controle.get("ultimo_dia_anunciado") == ontem:
            return  # já anunciou o dia de ontem, nada a fazer

        # Manda só UMA vez, pro servidor dono do canal de anúncio — antes o
        # código percorria todos os servidores em que o bot está (self.bot.guilds)
        # chamando get_channel(CANAL_RANKING_ID), que é uma busca GLOBAL (não por
        # servidor). Se o bot estiver em mais de um servidor, isso repetia o
        # mesmo anúncio, um por servidor, sempre no mesmo canal — daí a
        # mensagem duplicada.
        canal = self.bot.get_channel(CANAL_RANKING_ID)
        if canal is None:
            print(f"[MAIS_ATIVO] ⚠️ Canal {CANAL_RANKING_ID} não encontrado.")
            return

        try:
            await self._anunciar_mais_ativo(canal.guild, ontem)
        except Exception as e:
            print(f"[MAIS_ATIVO] ⚠️ Erro ao anunciar em {canal.guild}: {e}")

        controle["ultimo_dia_anunciado"] = ontem
        _salvar_controle(controle)

    @verificar_virada_dia.before_loop
    async def antes_verificar(self):
        await self.bot.wait_until_ready()

    # ── !mais-ativo [ontem|hoje] — comando manual pra staff testar/consultar ──
    @commands.command(name="mais-ativo")
    @commands.has_permissions(administrator=True)
    async def mais_ativo_manual(self, ctx: commands.Context, quando: str = "ontem"):
        dia = _hoje_str() if quando.strip().lower() == "hoje" else _ontem_str()
        await self._anunciar_mais_ativo(ctx.guild, dia)
        await ctx.send(f"✅ Ranking de `{dia}` verificado (veja o canal de jogadores).", delete_after=6)

    @mais_ativo_manual.error
    async def mais_ativo_manual_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(MaisAtivo(bot))
