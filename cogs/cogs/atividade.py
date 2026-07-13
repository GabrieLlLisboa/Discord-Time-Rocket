import discord
from discord.ext import commands, tasks
import os
from datetime import datetime, timedelta, timezone

from cogs.players import CARGOS as _CARGOS_JOGADORES
from cogs.json_store import ler_json, salvar_json

RANKS_ORDENADOS = [c for c in _CARGOS_JOGADORES if c["secao"] == "rank"]
RANK_IDS_SET = {c["id"] for c in RANKS_ORDENADOS}

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

# Único usuário que pode rodar o !ativar (marcar alguém como ativo manualmente)
IDS_AUTORIZADOS = {1487452210605588592, 1421693641184772147}

DATA_PATH = "data/atividade.json"
CONFIG_PATH = "data/atividade_config.json"


def _config_padrao() -> dict:
    return {
        "inicio": datetime(2026, 7, 1, 0, 0, tzinfo=BR_TZ).isoformat(),
        "fim": datetime(2026, 7, 10, 0, 0, tzinfo=BR_TZ).isoformat(),
        "mensagens_minimas": 10,
        "segundos_call_minimo": 15 * 60,
    }


def _ler_config() -> dict:
    return ler_json(CONFIG_PATH, _config_padrao)


def _salvar_config(config: dict):
    salvar_json(CONFIG_PATH, config)


# Config carregada uma vez na importação do módulo. Depois disso, só é alterada
# via aplicar_novo_periodo() (chamado pelo botão "Recomeçar Período de Avaliação").
_config_inicial = _ler_config()
INICIO_PERIODO = datetime.fromisoformat(_config_inicial["inicio"])
FIM_PERIODO = datetime.fromisoformat(_config_inicial["fim"])
MENSAGENS_MINIMAS = _config_inicial["mensagens_minimas"]          # precisa ser MAIOR que isso
SEGUNDOS_CALL_MINIMO = _config_inicial["segundos_call_minimo"]    # precisa ser MAIOR que isso


def limites_atuais() -> tuple:
    """(mensagens_minimas, segundos_call_minimo) atuais — sempre em dia, mesmo após um /recomeçar período."""
    return MENSAGENS_MINIMAS, SEGUNDOS_CALL_MINIMO


def entrou_durante_periodo(membro: discord.Member) -> bool:
    """
    True se o membro entrou no servidor DEPOIS do período de avaliação já ter
    começado (e antes dele acabar) — ou seja, não teve o período completo pra
    provar atividade. Esses membros não contam nem como ativos nem como
    inativos em nenhuma lista/checagem.
    """
    if membro.joined_at is None:
        return False
    return INICIO_PERIODO <= membro.joined_at <= FIM_PERIODO


def _periodo_ativo() -> bool:
    agora = datetime.now(BR_TZ)
    return INICIO_PERIODO <= agora < FIM_PERIODO


def _ler() -> dict:
    return ler_json(DATA_PATH, {})


def _salvar(dados: dict):
    salvar_json(DATA_PATH, dados)


# ─────────────────────────────────────────────
#  Painel !setup-sistema-atividade
# ─────────────────────────────────────────────
class ConfirmarResetAtivosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmar", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: "Atividade" = interaction.client.get_cog("Atividade")
        await cog.reiniciar_ativos(interaction)
        self.stop()

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelado, nada foi alterado.", view=None)
        self.stop()


class NovoPeriodoModal(discord.ui.Modal, title="🔄 Novo Período de Avaliação"):
    dias = discord.ui.TextInput(label="Quantos dias vai durar?", placeholder="Ex: 10", max_length=4)
    reiniciar = discord.ui.TextInput(label="Reiniciar os ativos também? (sim/não)", placeholder="sim ou não", max_length=5)
    mensagens = discord.ui.TextInput(label="Mensagens mínimas p/ ser ativo", placeholder="Ex: 10", max_length=6)
    minutos_call = discord.ui.TextInput(label="Minutos de call p/ ser ativo", placeholder="Ex: 15", max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        cog: "Atividade" = interaction.client.get_cog("Atividade")
        await cog.aplicar_novo_periodo(
            interaction,
            self.dias.value,
            self.mensagens.value,
            self.minutos_call.value,
            self.reiniciar.value,
        )


class SetupAtividadeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reiniciar os Ativos", emoji="🔁", style=discord.ButtonStyle.danger, custom_id="atividade_reiniciar_ativos")
    async def btn_reiniciar_ativos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in IDS_AUTORIZADOS:
            await interaction.response.send_message("❌ Você não tem permissão pra usar isso.", ephemeral=True)
            return
        await interaction.response.send_message(
            "⚠️ Isso vai **zerar o progresso** (mensagens, tempo de call e status ativo) de **todo mundo**, "
            "mantendo o período atual. Tem certeza?",
            view=ConfirmarResetAtivosView(),
            ephemeral=True,
        )

    @discord.ui.button(label="Recomeçar Período de Avaliação", emoji="🔄", style=discord.ButtonStyle.primary, custom_id="atividade_recomecar_periodo")
    async def btn_recomecar_periodo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in IDS_AUTORIZADOS:
            await interaction.response.send_message("❌ Você não tem permissão pra usar isso.", ephemeral=True)
            return
        await interaction.response.send_modal(NovoPeriodoModal())


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
    # Regra: só conta tempo de call se a pessoa estiver acompanhada por pelo
    # menos +1 humano no canal. Se ficar sozinha, o cronômetro dela para (mas
    # não é perdido: quando alguém entra de novo no canal, volta a contar).
    async def _atualizar_canal(self, canal: discord.VoiceChannel, agora: datetime):
        humanos = [m for m in canal.members if not m.bot]
        acompanhado = len(humanos) >= 2
        mudou = False

        for m in humanos:
            if acompanhado and m.id not in self.voz_entrada:
                if _periodo_ativo():
                    self.voz_entrada[m.id] = agora
            elif not acompanhado and m.id in self.voz_entrada:
                entrada = self.voz_entrada.pop(m.id)
                if _periodo_ativo():
                    decorrido = (agora - entrada).total_seconds()
                    registro = self._registro(m.id)
                    registro["voz_segundos"] += max(decorrido, 0)
                    mudou = True

        if mudou:
            _salvar(self.dados)
        for m in humanos:
            await self._checar_e_anunciar(m)

    @commands.Cog.listener()
    async def on_voice_state_update(self, membro: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        if membro.bot:
            return

        agora = datetime.now(timezone.utc)
        canal_afk = membro.guild.afk_channel

        antes_canal = antes.channel if (antes.channel is not None and antes.channel != canal_afk) else None
        depois_canal = depois.channel if (depois.channel is not None and depois.channel != canal_afk) else None

        if antes_canal == depois_canal:
            return  # só mudou mute/deaf/etc — não trocou de canal, nada a recalcular

        # Encerra a sessão de contagem do próprio membro (se estava rodando)
        if membro.id in self.voz_entrada:
            entrada = self.voz_entrada.pop(membro.id)
            if _periodo_ativo():
                decorrido = (agora - entrada).total_seconds()
                registro = self._registro(membro.id)
                registro["voz_segundos"] += max(decorrido, 0)
                _salvar(self.dados)
                await self._checar_e_anunciar(membro)

        # Reavalia o canal antigo — quem ficou lá pode ter sobrado sozinho agora
        if antes_canal is not None:
            await self._atualizar_canal(antes_canal, agora)

        # Reavalia o canal novo — o próprio membro entra na contagem se tiver
        # companhia, e quem já estava lá sozinho passa a contar também
        if depois_canal is not None:
            await self._atualizar_canal(depois_canal, agora)

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
                await self._atualizar_canal(canal, agora)
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


    # ── Reinicia o progresso de todo mundo (mantém o período atual) ─────────
    async def reiniciar_ativos(self, interaction: discord.Interaction):
        self.dados = {}
        _salvar(self.dados)
        await interaction.response.edit_message(
            content="✅ Ativos reiniciados! Todo mundo volta a contar mensagens/call do zero.",
            view=None,
        )
        print(f"[ATIVIDADE] 🔁 Ativos reiniciados por {interaction.user}.")

    # ── Aplica um novo período de avaliação (chamado pelo modal) ────────────
    async def aplicar_novo_periodo(self, interaction: discord.Interaction, dias_str: str, msgs_str: str, call_min_str: str, reiniciar_str: str):
        try:
            dias = int(dias_str.strip())
            msgs_min = int(msgs_str.strip())
            call_min = int(call_min_str.strip())
        except ValueError:
            await interaction.response.send_message("❌ Dias, mensagens e minutos de call precisam ser números.", ephemeral=True)
            return

        if dias <= 0 or msgs_min < 0 or call_min < 0:
            await interaction.response.send_message("❌ Valores inválidos (dias tem que ser maior que 0).", ephemeral=True)
            return

        reiniciar = reiniciar_str.strip().lower() in ("sim", "s", "yes", "y")

        global INICIO_PERIODO, FIM_PERIODO, MENSAGENS_MINIMAS, SEGUNDOS_CALL_MINIMO
        INICIO_PERIODO = datetime.now(BR_TZ)
        FIM_PERIODO = INICIO_PERIODO + timedelta(days=dias)
        MENSAGENS_MINIMAS = msgs_min
        SEGUNDOS_CALL_MINIMO = call_min * 60

        _salvar_config({
            "inicio": INICIO_PERIODO.isoformat(),
            "fim": FIM_PERIODO.isoformat(),
            "mensagens_minimas": MENSAGENS_MINIMAS,
            "segundos_call_minimo": SEGUNDOS_CALL_MINIMO,
        })

        if reiniciar:
            self.dados = {}
            _salvar(self.dados)

        # Se o período anterior já tinha acabado, o loop de verificação tinha
        # parado sozinho — reativa ele pro período novo.
        if not self.verificar_fim_periodo.is_running():
            self.verificar_fim_periodo.start()

        await interaction.response.send_message(
            "✅ **Novo período de avaliação iniciado!**\n\n"
            f"📅 **{dias}** dias — até <t:{int(FIM_PERIODO.timestamp())}:F>\n"
            f"💬 Meta: mais de **{msgs_min}** mensagens\n"
            f"🎙️ Ou mais de **{call_min}** minutos em call\n"
            f"🔁 Ativos reiniciados: **{'Sim' if reiniciar else 'Não'}**\n\n"
            "ℹ️ Quem entrar no servidor **durante** esse período fica de fora da "
            "contagem de ativos/inativos (não é justo cobrar atividade de quem "
            "não teve o período inteiro pra jogar).",
            ephemeral=True,
        )
        print(f"[ATIVIDADE] 🔄 Novo período aplicado por {interaction.user}: {dias} dias, msgs>{msgs_min}, call>{call_min}min, reset={reiniciar}.")

    # ── !setup-sistema-atividade — painel de controle (staff autorizada) ────
    @commands.command(name="setup-sistema-atividade", hidden=True)
    async def setup_sistema_atividade(self, ctx: commands.Context):
        if ctx.author.id not in IDS_AUTORIZADOS:
            return

        embed = discord.Embed(
            title="⚙️ Sistema de Atividade",
            description=(
                "Painel de controle do período de avaliação de atividade.\n\n"
                f"📅 Período atual: **{INICIO_PERIODO.strftime('%d/%m/%Y %H:%M')}** até "
                f"**{FIM_PERIODO.strftime('%d/%m/%Y %H:%M')}**\n"
                f"💬 Meta: mais de **{MENSAGENS_MINIMAS}** mensagens\n"
                f"🎙️ Ou mais de **{SEGUNDOS_CALL_MINIMO // 60}** minutos em call\n\n"
                "🔁 **Reiniciar os Ativos** — zera o progresso de todo mundo, mantendo o período atual.\n"
                "🔄 **Recomeçar Período de Avaliação** — abre um formulário pra configurar um período novo "
                "(quantos dias, meta de mensagens, meta de call, e se reinicia os ativos junto)."
            ),
            color=0x5865F2,
        )
        await ctx.send(embed=embed, view=SetupAtividadeView())

    @setup_sistema_atividade.error
    async def setup_sistema_atividade_error(self, ctx, error):
        if ctx.author.id in IDS_AUTORIZADOS:
            await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)

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
        ignorados_grace = 0
        for membro in ctx.guild.members:
            if membro.bot:
                continue
            if entrou_durante_periodo(membro):
                ignorados_grace += 1
                continue
            registro = self.dados.get(str(membro.id))
            if registro is None or not registro.get("anunciado", False):
                inativos.append(membro)

        total_membros = sum(1 for m in ctx.guild.members if not m.bot) - ignorados_grace
        percentual = (len(inativos) / total_membros * 100) if total_membros else 0

        if not inativos:
            await ctx.send("✅ Ninguém inativo no momento — todo mundo já bateu a meta!")
            await ctx.send(f"**0** inativos\nIsso representa **0%** dos membros.")
            return

        inativos.sort(key=lambda m: m.display_name.lower())

        # ── Top dos ranks com mais gente inativa ────────────────────────────
        contagem_por_rank = {c["id"]: 0 for c in RANKS_ORDENADOS}
        sem_rank = 0
        for membro in inativos:
            rank_id = next((r.id for r in membro.roles if r.id in RANK_IDS_SET), None)
            if rank_id is not None:
                contagem_por_rank[rank_id] += 1
            else:
                sem_rank += 1

        top_ranks = [
            (c, contagem_por_rank[c["id"]]) for c in RANKS_ORDENADOS if contagem_por_rank[c["id"]] > 0
        ]
        top_ranks.sort(key=lambda par: par[1], reverse=True)
        if sem_rank > 0:
            top_ranks.append(({"nome": "Sem rank", "emoji": "❔"}, sem_rank))

        linhas_top = [
            f"**{i+1}.** {c['emoji']} {c['nome']} — **{qtd}** inativo(s)"
            for i, (c, qtd) in enumerate(top_ranks)
        ]

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
        embed.set_footer(text=f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')}" + (f" • {ignorados_grace} entrou durante o período (não contado)" if ignorados_grace else ""))

        if linhas_top:
            embed.add_field(name="🏆 Top ranks com mais inativos", value="\n".join(linhas_top), inline=False)

        for idx, bloco in enumerate(blocos, start=1):
            nome_campo = "Inativos" if len(blocos) == 1 else f"Inativos ({idx}/{len(blocos)})"
            embed.add_field(name=nome_campo, value="\n".join(bloco), inline=False)

            # Limite de 25 campos por embed — se passar disso, manda e abre um novo embed
            if len(embed.fields) == 25 and idx != len(blocos):
                await ctx.send(embed=embed)
                embed = discord.Embed(color=0xED4245)

        await ctx.send(embed=embed)
        await ctx.send(f"**{len(inativos)}** inativos\nIsso representa **{percentual:.1f}%** dos membros.")

    @listar_inativos.error
    async def listar_inativos_error(self, ctx, error):
        if ctx.author.id in IDS_AUTORIZADOS:
            await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Atividade(bot))
