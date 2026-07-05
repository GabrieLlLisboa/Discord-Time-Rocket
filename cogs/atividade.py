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

# Único usuário que pode rodar o !ativar (marcar alguém como ativo manualmente)
IDS_AUTORIZADOS = {1487452210605588592, 1421693641184772147}

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
    # OBS: "voz_segundos" é cumulativo — soma o tempo de TODAS as sessões de call
    # da pessoa dentro do período (mesmo em dias diferentes). Nunca é resetado
    # durante o período, então "5 min hoje + 20 min amanhã" vira 25 min total.
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


    # ── !ativar <id> — marca alguém como ativo manualmente ──────────────────
    @commands.command(name="ativar", hidden=True)
    async def marcar_ativo_manual(self, ctx: commands.Context, membro_id: str = None):
        # Só o usuário autorizado pode usar — pra qualquer outra pessoa, o bot finge que o comando não existe
        if ctx.author.id not in IDS_AUTORIZADOS:
            return

        if membro_id is None:
            await ctx.send("⚠️ Uso: `!ativar <id_do_usuário>` (ou marque a pessoa com @)", delete_after=6)
            return

        membro_id_limpo = membro_id.strip("<@!>")
        if not membro_id_limpo.isdigit():
            await ctx.send("⚠️ ID inválido. Uso: `!ativar <id_do_usuário>`.", delete_after=6)
            return

        membro = ctx.guild.get_member(int(membro_id_limpo))
        if membro is None:
            await ctx.send("❌ Não encontrei esse membro neste servidor.", delete_after=6)
            return

        registro = self._registro(membro.id)
        if registro["anunciado"]:
            await ctx.send(f"⚠️ **{membro.display_name}** já estava marcado como ativo.", delete_after=6)
            return

        registro["anunciado"] = True
        _salvar(self.dados)

        canal = self.bot.get_channel(CANAL_ANUNCIO_ID)
        if canal is not None:
            embed = discord.Embed(
                title="✅ Jogador ativo!",
                description=f"{membro.mention} se demonstrou **ativo** no servidor!",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Motivo", value="✅ Marcado manualmente pela staff", inline=False)
            embed.set_footer(text=f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')}")
            try:
                await canal.send(embed=embed)
            except discord.Forbidden:
                print(f"[ATIVIDADE] ⚠️ Sem permissão para mandar mensagem no canal {CANAL_ANUNCIO_ID}.")

        # Se a pessoa estiver em quarentena, tira ela automaticamente
        aviso_extra = ""
        demote_cog = self.bot.get_cog("Demote")
        if demote_cog is not None:
            saiu = await demote_cog.forcar_saida_quarentena(membro, motivo="Marcado como ativo manualmente via !ativar")
            if saiu:
                aviso_extra = " Ela também foi **tirada da quarentena** automaticamente."

        await ctx.send(f"✅ **{membro.display_name}** foi marcado como ativo.{aviso_extra}", delete_after=10)
        print(f"[ATIVIDADE] ✅ {membro} marcado manualmente como ativo por {ctx.author}.")

    @marcar_ativo_manual.error
    async def marcar_ativo_manual_error(self, ctx, error):
        if ctx.author.id in IDS_AUTORIZADOS:
            await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)

    # ── !listar-inativos — lista quem ainda não bateu a meta de atividade ────
    @commands.command(name="listar-inativos", hidden=True)
    async def listar_inativos(self, ctx: commands.Context):
        # Só o usuário autorizado pode usar — pra qualquer outra pessoa, o bot finge que o comando não existe
        if ctx.author.id not in IDS_AUTORIZADOS:
            return

        inativos = []
        for membro in ctx.guild.members:
            if membro.bot:
                continue
            registro = self.dados.get(str(membro.id))
            if registro is None or not registro.get("anunciado", False):
                inativos.append(membro)

        if not inativos:
            await ctx.send("✅ Ninguém inativo no momento — todo mundo já bateu a meta!")
            return

        inativos.sort(key=lambda m: m.display_name.lower())

        linhas = []
        for membro in inativos:
            registro = self.dados.get(str(membro.id), {"mensagens": 0, "voz_segundos": 0})
            minutos_call = int(registro.get("voz_segundos", 0) // 60)
            linhas.append(
                f"{membro.mention} — 💬 {registro.get('mensagens', 0)} msgs • 🎙️ {minutos_call} min"
            )

        # Quebra em blocos pra não estourar o limite de 1024 caracteres por campo
        BLOCO = 15
        blocos = [linhas[i:i + BLOCO] for i in range(0, len(linhas), BLOCO)]

        embed = discord.Embed(
            title="📋 Membros inativos",
            description=f"Total: **{len(inativos)}** membro(s) que ainda não bateram a meta.",
            color=0xED4245,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')}")

        for idx, bloco in enumerate(blocos, start=1):
            nome_campo = "Inativos" if len(blocos) == 1 else f"Inativos ({idx}/{len(blocos)})"
            embed.add_field(name=nome_campo, value="\n".join(bloco), inline=False)

            # Limite de 25 campos por embed — se passar disso, manda e abre um novo embed
            if len(embed.fields) == 25 and idx != len(blocos):
                await ctx.send(embed=embed)
                embed = discord.Embed(color=0xED4245)

        await ctx.send(embed=embed)

    @listar_inativos.error
    async def listar_inativos_error(self, ctx, error):
        if ctx.author.id in IDS_AUTORIZADOS:
            await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Atividade(bot))
