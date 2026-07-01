import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────────
#  Cog: Rastreador de Atividade
#  Arquivo: cogs/atividade.py
#
#  Monitora, num período fixo, quem manda mais de
#  10 mensagens OU fica mais de 15 minutos em call.
#  Assim que a pessoa bate a meta, o bot anuncia
#  no canal configurado (só uma vez por pessoa).
# ─────────────────────────────────────────────

CANAL_ANUNCIO_ID = 1521708231620034600

BR_TZ = timezone(timedelta(hours=-3))
INICIO_PERIODO = datetime(2026, 7, 1, 0, 0, tzinfo=BR_TZ)
FIM_PERIODO    = datetime(2026, 7, 10, 0, 0, tzinfo=BR_TZ)

MENSAGENS_MINIMAS   = 10          # precisa ser MAIOR que isso
SEGUNDOS_CALL_MINIMO = 15 * 60    # precisa ser MAIOR que isso (15 min)

DATA_PATH = "data/atividade.json"


def _periodo_ativo() -> bool:
    agora = datetime.now(BR_TZ)
    return INICIO_PERIODO <= agora < FIM_PERIODO


def _ler() -> dict:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _salvar(dados: dict):
    os.makedirs("data", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


class Atividade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = _ler()  # { "user_id": {"mensagens": int, "voz_segundos": float, "anunciado": bool} }
        self.voz_entrada = {}  # { user_id: datetime da última entrada em call (não persiste no restart) }
        self.verificar_fim_periodo.start()

    def cog_unload(self):
        self.verificar_fim_periodo.cancel()

    # ── Helpers internos ─────────────────────────────────────────────────────
    def _registro(self, user_id: int) -> dict:
        chave = str(user_id)
        if chave not in self.dados:
            self.dados[chave] = {"mensagens": 0, "voz_segundos": 0, "anunciado": False}
        return self.dados[chave]

    async def _checar_e_anunciar(self, membro: discord.Member):
        registro = self._registro(membro.id)
        if registro["anunciado"]:
            return

        bateu_mensagens = registro["mensagens"] > MENSAGENS_MINIMAS
        bateu_call = registro["voz_segundos"] > SEGUNDOS_CALL_MINIMO

        if not (bateu_mensagens or bateu_call):
            return

        registro["anunciado"] = True
        _salvar(self.dados)

        canal = self.bot.get_channel(CANAL_ANUNCIO_ID)
        if canal is None:
            print(f"[ATIVIDADE] ⚠️ Canal de anúncio ({CANAL_ANUNCIO_ID}) não encontrado.")
            return

        minutos_call = int(registro["voz_segundos"] // 60)
        motivo = []
        if bateu_mensagens:
            motivo.append(f"💬 **{registro['mensagens']}** mensagens")
        if bateu_call:
            motivo.append(f"🎙️ **{minutos_call}** minutos em call")

        embed = discord.Embed(
            title="✅ Jogador ativo!",
            description=f"{membro.mention} se demonstrou **ativo** no servidor!",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Motivo", value=" • ".join(motivo), inline=False)
        embed.set_footer(text=f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')}")

        try:
            await canal.send(embed=embed)
            print(f"[ATIVIDADE] ✅ {membro} anunciado como ativo.")
        except discord.Forbidden:
            print(f"[ATIVIDADE] ⚠️ Sem permissão para mandar mensagem no canal {CANAL_ANUNCIO_ID}.")

    # ── Mensagens ────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not _periodo_ativo():
            return

        registro = self._registro(message.author.id)
        registro["mensagens"] += 1
        _salvar(self.dados)

        await self._checar_e_anunciar(message.author)

    # ── Voz ──────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(self, membro: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        if membro.bot:
            return

        agora = datetime.now(timezone.utc)
        canal_afk = membro.guild.afk_channel

        entrou_em_call = depois.channel is not None and depois.channel != canal_afk
        saiu_da_call = antes.channel is not None and antes.channel != canal_afk and (
            depois.channel is None or depois.channel == canal_afk
        )

        # Encerrou tempo em call (saiu ou foi pro canal AFK) → soma o tempo
        if saiu_da_call and membro.id in self.voz_entrada:
            entrada = self.voz_entrada.pop(membro.id)
            if _periodo_ativo():
                decorrido = (agora - entrada).total_seconds()
                registro = self._registro(membro.id)
                registro["voz_segundos"] += max(decorrido, 0)
                _salvar(self.dados)
                await self._checar_e_anunciar(membro)
            return

        # Entrou em call agora (vindo de fora ou do AFK) → começa a contar
        if entrou_em_call and membro.id not in self.voz_entrada:
            if _periodo_ativo():
                self.voz_entrada[membro.id] = agora

    # ── Ao iniciar o bot: retoma contagem de quem já está em call ───────────────
    @commands.Cog.listener()
    async def on_ready(self):
        if not _periodo_ativo():
            return
        agora = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            canal_afk = guild.afk_channel
            for canal in guild.voice_channels:
                if canal == canal_afk:
                    continue
                for membro in canal.members:
                    if not membro.bot and membro.id not in self.voz_entrada:
                        self.voz_entrada[membro.id] = agora
        print("[ATIVIDADE] ✅ Rastreador de atividade pronto.")

    # ── Encerra a contagem de call pendente quando o período acabar ────────────
    @tasks.loop(minutes=1)
    async def verificar_fim_periodo(self):
        await self.bot.wait_until_ready()
        agora = datetime.now(BR_TZ)
        if agora < FIM_PERIODO:
            return

        # Período encerrado: fecha o tempo de quem ainda estava em call
        if self.voz_entrada:
            agora_utc = datetime.now(timezone.utc)
            for user_id, entrada in list(self.voz_entrada.items()):
                decorrido = (agora_utc - entrada).total_seconds()
                registro = self._registro(user_id)
                registro["voz_segundos"] += max(decorrido, 0)
                self.voz_entrada.pop(user_id, None)
            _salvar(self.dados)

            for guild in self.bot.guilds:
                for user_id in list(self.dados.keys()):
                    membro = guild.get_member(int(user_id))
                    if membro:
                        await self._checar_e_anunciar(membro)

        print("[ATIVIDADE] 🏁 Período de verificação de atividade encerrado.")
        self.verificar_fim_periodo.cancel()

    @verificar_fim_periodo.before_loop
    async def antes_verificar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Atividade(bot))
