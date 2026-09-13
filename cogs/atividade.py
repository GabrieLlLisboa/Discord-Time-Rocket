import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

from cogs.players import CARGOS as _CARGOS_JOGADORES
from cogs.json_store import ler_json, salvar_json

RANKS_ORDENADOS = [c for c in _CARGOS_JOGADORES if c["secao"] == "rank"]
RANK_IDS_SET = {c["id"] for c in RANKS_ORDENADOS}


CANAL_ANUNCIO_ID = 1521708231620034600

BR_TZ = timezone(timedelta(hours=-3))


IDS_AUTORIZADOS = {1487452210605588592, 1421693641184772147}

DATA_PATH = "data/atividade.json"
CONFIG_PATH = "data/atividade_config.json"


def _somar_meses(dt: datetime, meses: int) -> datetime:
    """Soma `meses` meses numa data, ajustando ano/mês corretamente (sem depender de dateutil)."""
    mes_total = dt.month - 1 + meses
    ano = dt.year + mes_total // 12
    mes = mes_total % 12 + 1
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(dt.day, ultimo_dia)
    return dt.replace(year=ano, month=mes, day=dia)


def _config_padrao() -> dict:
    # Período de atividade: começa hoje e dura 2 meses.
    inicio = datetime(2026, 9, 12, 0, 0, tzinfo=BR_TZ)
    return {
        "inicio": inicio.isoformat(),
        "fim": _somar_meses(inicio, 2).isoformat(),
        # Sistema de PONTOS: 1 mensagem = 1 ponto; a cada N segundos em call = 1 ponto.
        # Pontos de mensagem + pontos de call se somam. Meta: mais de `meta_pontos`.
        "meta_pontos": 25,
        "pontos_por_mensagem": 1,
        "segundos_por_ponto_call": 5 * 60,  # 5 minutos de call = 1 ponto
    }


def _ler_config() -> dict:
    return ler_json(CONFIG_PATH, _config_padrao)


def _salvar_config(config: dict):
    salvar_json(CONFIG_PATH, config)


_config_inicial = _ler_config()
INICIO_PERIODO = datetime.fromisoformat(_config_inicial["inicio"])
FIM_PERIODO = datetime.fromisoformat(_config_inicial["fim"])
META_PONTOS = _config_inicial.get("meta_pontos", 25)
PONTOS_POR_MENSAGEM = _config_inicial.get("pontos_por_mensagem", 1)
SEGUNDOS_POR_PONTO_CALL = _config_inicial.get("segundos_por_ponto_call", 5 * 60)


def limites_atuais() -> tuple:
    """(meta_pontos, segundos_por_ponto_call) atuais — sempre em dia, mesmo após um /recomeçar período.
    Mantido por compatibilidade com outros cogs (ex: grafico_jogadores.py)."""
    return META_PONTOS, SEGUNDOS_POR_PONTO_CALL


def pontos_do_periodo(registro: dict) -> int:
    """Quantos pontos de atividade o membro tem NO PERÍODO ATUAL (reseta quando o período reinicia)."""
    pontos_msg = registro.get("mensagens", 0) * PONTOS_POR_MENSAGEM
    pontos_call = registro.get("voz_segundos", 0) // SEGUNDOS_POR_PONTO_CALL
    return int(pontos_msg + pontos_call)


def pontos_totais_acumulados(registro: dict) -> int:
    """Pontos ACUMULADOS de todos os tempos (nunca reseta, mesmo quando o período reinicia)."""
    pontos_msg = registro.get("mensagens_total", 0) * PONTOS_POR_MENSAGEM
    pontos_call = registro.get("voz_segundos_total", 0) // SEGUNDOS_POR_PONTO_CALL
    return int(pontos_msg + pontos_call)


def atingiu_meta(registro: dict) -> bool:
    return pontos_do_periodo(registro) > META_PONTOS


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


def _esta_mutado(voice_state) -> bool:
    """
    True se o membro está mutado (self-mute OU mute do servidor) ou se
    simplesmente não tem voice_state (não está em call). Enquanto mutado,
    o tempo em call não conta ponto.
    """
    if voice_state is None:
        return True
    return bool(voice_state.self_mute or voice_state.mute)


def _ler() -> dict:
    return ler_json(DATA_PATH, {})


def _salvar(dados: dict):
    salvar_json(DATA_PATH, dados)


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
    dias = discord.ui.TextInput(label="Quantos dias vai durar?", placeholder="Ex: 60 (2 meses)", max_length=4)
    reiniciar = discord.ui.TextInput(label="Reiniciar os ativos também? (sim/não)", placeholder="sim ou não", max_length=5)
    mensagens = discord.ui.TextInput(label="Meta de pontos p/ ser ativo", placeholder="Ex: 25", max_length=6)
    minutos_call = discord.ui.TextInput(label="Minutos de call = 1 ponto", placeholder="Ex: 5", max_length=6)

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
        self.dados = _ler()
        self.voz_entrada = {}
        self.verificar_fim_periodo.start()

    def cog_unload(self):
        self.verificar_fim_periodo.cancel()


    def _registro(self, user_id: int) -> dict:
        chave = str(user_id)
        if chave not in self.dados:
            self.dados[chave] = {
                "mensagens": 0,
                "voz_segundos": 0,
                "mensagens_total": 0,
                "voz_segundos_total": 0,
                "anunciado": False,
            }
        else:
            # Migração: registros antigos podem não ter os campos "_total" (acumulado histórico).
            self.dados[chave].setdefault("mensagens_total", self.dados[chave].get("mensagens", 0))
            self.dados[chave].setdefault("voz_segundos_total", self.dados[chave].get("voz_segundos", 0))
        return self.dados[chave]

    async def _checar_e_anunciar(self, membro: discord.Member):
        registro = self._registro(membro.id)
        if registro["anunciado"]:
            return

        pontos = pontos_do_periodo(registro)
        if pontos <= META_PONTOS:
            return

        registro["anunciado"] = True
        _salvar(self.dados)

        canal = self.bot.get_channel(CANAL_ANUNCIO_ID)
        if canal is None:
            print(f"[ATIVIDADE] ⚠️ Canal de anúncio ({CANAL_ANUNCIO_ID}) não encontrado.")
            return

        minutos_call = int(registro["voz_segundos"] // 60)
        pontos_msg = registro["mensagens"] * PONTOS_POR_MENSAGEM
        pontos_call = registro["voz_segundos"] // SEGUNDOS_POR_PONTO_CALL
        motivo = [
            f"💬 **{registro['mensagens']}** mensagens (**{pontos_msg}** pts)",
            f"🎙️ **{minutos_call}** minutos em call (**{pontos_call}** pts)",
        ]

        embed = discord.Embed(
            title="✅ Jogador ativo!",
            description=f"{membro.mention} bateu a meta de atividade do período com **{pontos}** pontos!",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Como conseguiu os pontos", value=" • ".join(motivo), inline=False)
        embed.set_footer(text=f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')} • Meta: {META_PONTOS} pontos")

        try:
            await canal.send(embed=embed)
            print(f"[ATIVIDADE] ✅ {membro} anunciado como ativo.")
        except discord.Forbidden:
            print(f"[ATIVIDADE] ⚠️ Sem permissão para mandar mensagem no canal {CANAL_ANUNCIO_ID}.")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not _periodo_ativo():
            return

        registro = self._registro(message.author.id)
        registro["mensagens"] += 1
        registro["mensagens_total"] += 1
        _salvar(self.dados)

        await self._checar_e_anunciar(message.author)


    async def _atualizar_canal(self, canal: discord.VoiceChannel, agora: datetime):
        humanos = [m for m in canal.members if not m.bot]
        acompanhado = len(humanos) >= 2
        mudou = False

        for m in humanos:
            # Só conta ponto de call se: tiver mais alguém no canal (não sozinho)
            # E o próprio membro estiver desmutado (nem self-mute, nem mute do servidor).
            pode_contar = acompanhado and not _esta_mutado(m.voice)

            if pode_contar and m.id not in self.voz_entrada:
                if _periodo_ativo():
                    self.voz_entrada[m.id] = agora
            elif not pode_contar and m.id in self.voz_entrada:
                entrada = self.voz_entrada.pop(m.id)
                if _periodo_ativo():
                    decorrido = max((agora - entrada).total_seconds(), 0)
                    registro = self._registro(m.id)
                    registro["voz_segundos"] += decorrido
                    registro["voz_segundos_total"] += decorrido
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

        # Se o membro só mutou/desmutou (sem trocar de canal), precisamos
        # recalcular mesmo assim — é isso que liga/desliga a contagem de pontos.
        mudou_mute = _esta_mutado(antes) != _esta_mutado(depois)

        if antes_canal == depois_canal and not mudou_mute:
            return

        if antes_canal != depois_canal and membro.id in self.voz_entrada:
            entrada = self.voz_entrada.pop(membro.id)
            if _periodo_ativo():
                decorrido = max((agora - entrada).total_seconds(), 0)
                registro = self._registro(membro.id)
                registro["voz_segundos"] += decorrido
                registro["voz_segundos_total"] += decorrido
                _salvar(self.dados)
                await self._checar_e_anunciar(membro)


        if antes_canal is not None:
            await self._atualizar_canal(antes_canal, agora)


        if depois_canal is not None:
            await self._atualizar_canal(depois_canal, agora)


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


    @tasks.loop(minutes=1)
    async def verificar_fim_periodo(self):
        await self.bot.wait_until_ready()
        agora = datetime.now(BR_TZ)
        if agora < FIM_PERIODO:
            return

        try:

            if self.voz_entrada:
                agora_utc = datetime.now(timezone.utc)
                for user_id, entrada in list(self.voz_entrada.items()):
                    decorrido = max((agora_utc - entrada).total_seconds(), 0)
                    registro = self._registro(user_id)
                    registro["voz_segundos"] += decorrido
                    registro["voz_segundos_total"] += decorrido
                    self.voz_entrada.pop(user_id, None)
                _salvar(self.dados)

                for guild in self.bot.guilds:
                    for user_id in list(self.dados.keys()):
                        membro = guild.get_member(int(user_id))
                        if membro:
                            await self._checar_e_anunciar(membro)

            print("[ATIVIDADE] 🏁 Período de verificação de atividade encerrado.")
            self.verificar_fim_periodo.cancel()
        except Exception as e:


            print(f"[ATIVIDADE] ⚠️ Erro ao encerrar período: {e}")

    @verificar_fim_periodo.before_loop
    async def antes_verificar(self):
        await self.bot.wait_until_ready()


    async def reiniciar_ativos(self, interaction: discord.Interaction):
        # Zera só o progresso DO PERÍODO (mensagens/call/anunciado). Os pontos
        # acumulados de todos os tempos (mensagens_total/voz_segundos_total)
        # são preservados — é assim que o ranking de pontos totais continua
        # somando de período em período.
        for registro in self.dados.values():
            registro["mensagens"] = 0
            registro["voz_segundos"] = 0
            registro["anunciado"] = False
        _salvar(self.dados)
        await interaction.response.edit_message(
            content="✅ Ativos reiniciados! Todo mundo volta a contar mensagens/call do zero neste período "
                    "(os **pontos totais acumulados** do ranking continuam guardados, sem resetar).",
            view=None,
        )
        print(f"[ATIVIDADE] 🔁 Ativos reiniciados por {interaction.user} (pontos acumulados preservados).")


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

        global INICIO_PERIODO, FIM_PERIODO, META_PONTOS, SEGUNDOS_POR_PONTO_CALL
        INICIO_PERIODO = datetime.now(BR_TZ)
        FIM_PERIODO = INICIO_PERIODO + timedelta(days=dias)
        META_PONTOS = msgs_min
        SEGUNDOS_POR_PONTO_CALL = call_min * 60

        _salvar_config({
            "inicio": INICIO_PERIODO.isoformat(),
            "fim": FIM_PERIODO.isoformat(),
            "meta_pontos": META_PONTOS,
            "pontos_por_mensagem": PONTOS_POR_MENSAGEM,
            "segundos_por_ponto_call": SEGUNDOS_POR_PONTO_CALL,
        })

        if reiniciar:
            # Preserva os pontos acumulados de todos os tempos, zera só o período.
            for registro in self.dados.values():
                registro["mensagens"] = 0
                registro["voz_segundos"] = 0
                registro["anunciado"] = False
            _salvar(self.dados)


        if not self.verificar_fim_periodo.is_running():
            self.verificar_fim_periodo.start()

        await interaction.response.send_message(
            "✅ **Novo período de avaliação iniciado!**\n\n"
            f"📅 **{dias}** dias — até <t:{int(FIM_PERIODO.timestamp())}:F>\n"
            f"🏆 Meta: mais de **{msgs_min}** pontos (1 msg = 1 pt, {call_min} min de call = 1 pt)\n"
            f"🔁 Ativos reiniciados: **{'Sim' if reiniciar else 'Não'}** (pontos acumulados no ranking nunca são apagados)\n\n"
            "ℹ️ Quem entrar no servidor **durante** esse período fica de fora da "
            "contagem de ativos/inativos (não é justo cobrar atividade de quem "
            "não teve o período inteiro pra jogar).",
            ephemeral=True,
        )
        print(f"[ATIVIDADE] 🔄 Novo período aplicado por {interaction.user}: {dias} dias, meta={msgs_min}pts, {call_min}min/pt, reset={reiniciar}.")


    @commands.command(name="atividade", aliases=["setup-sistema-atividade"], hidden=True)
    async def setup_sistema_atividade(self, ctx: commands.Context):
        if ctx.author.id not in IDS_AUTORIZADOS:
            return

        embed = discord.Embed(
            title="⚙️ Sistema de Atividade",
            description=(
                "Painel de controle do período de avaliação de atividade.\n\n"
                f"📅 Período atual: **{INICIO_PERIODO.strftime('%d/%m/%Y %H:%M')}** até "
                f"**{FIM_PERIODO.strftime('%d/%m/%Y %H:%M')}**\n"
                f"🏆 Meta: mais de **{META_PONTOS}** pontos\n"
                f"💬 1 mensagem = **{PONTOS_POR_MENSAGEM}** ponto\n"
                f"🎙️ A cada **{SEGUNDOS_POR_PONTO_CALL // 60}** minutos em call = **1** ponto\n"
                f"(mensagens e tempo em call se somam)\n\n"
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


    @commands.command(name="ativar", hidden=True)
    async def marcar_ativo_manual(self, ctx: commands.Context, membro_id: str = None):

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


    @commands.command(name="periodo-inativos", aliases=["listar-inativos"], hidden=True)
    async def listar_inativos(self, ctx: commands.Context):

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
            await ctx.send("**0** inativos\nIsso representa **0%** dos membros.")
            return

        inativos.sort(key=lambda m: m.display_name.lower())


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
            pontos = pontos_do_periodo(registro)
            linhas.append(
                f"{membro.mention} — 🏆 {pontos}/{META_PONTOS} pts • 💬 {registro.get('mensagens', 0)} msgs • 🎙️ {minutos_call} min"
            )


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


            if len(embed.fields) == 25 and idx != len(blocos):
                await ctx.send(embed=embed)
                embed = discord.Embed(color=0xED4245)

        await ctx.send(embed=embed)
        await ctx.send(f"**{len(inativos)}** inativos\nIsso representa **{percentual:.1f}%** dos membros.")

    @listar_inativos.error
    async def listar_inativos_error(self, ctx, error):
        if ctx.author.id in IDS_AUTORIZADOS:
            await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)


    @commands.command(name="pontuacao-total", aliases=["ranking-pontos", "rankingpontos", "pontos-ranking"])
    async def ranking_pontos(self, ctx: commands.Context):
        """
        Mostra o ranking de PONTOS TOTAIS ACUMULADOS (nunca reseta, mesmo quando
        o período de avaliação reinicia — só o progresso do período atual reseta).
        Aberto pra qualquer membro usar.
        """
        guild = ctx.guild

        linhas_ranking = []
        for user_id, registro in self.dados.items():
            membro = guild.get_member(int(user_id))
            if membro is None or membro.bot:
                continue
            total = pontos_totais_acumulados(registro)
            if total <= 0:
                continue
            linhas_ranking.append((membro, total, pontos_do_periodo(registro)))

        if not linhas_ranking:
            await ctx.send("📊 Ainda ninguém tem pontos registrados.")
            return

        linhas_ranking.sort(key=lambda t: t[1], reverse=True)

        medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
        linhas = []
        for i, (membro, total, pontos_periodo) in enumerate(linhas_ranking[:25], start=1):
            prefixo = medalhas.get(i, f"**{i}.**")
            linhas.append(
                f"{prefixo} {membro.mention} — **{total}** pontos totais "
                f"*({pontos_periodo} neste período)*"
            )

        embed = discord.Embed(
            title="🏆 Ranking de Pontos de Atividade",
            description="\n".join(linhas),
            color=0xD4A843,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text=(
                f"Pontos totais nunca resetam entre períodos • Período atual: "
                f"{INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')} "
                f"(meta: {META_PONTOS} pts)"
            )
        )
        await ctx.send(embed=embed)

    @ranking_pontos.error
    async def ranking_pontos_error(self, ctx, error):
        await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)


    @commands.command(name="periodo-pontuacao", aliases=["pontuacao-periodo"])
    async def periodo_pontuacao(self, ctx: commands.Context):
        """
        Mostra o ranking de pontos SÓ DO PERÍODO ATUAL (esse contador zera
        quando um novo período começa — diferente do !pontuacao-total, que
        nunca reseta). Aberto pra qualquer membro usar.
        """
        guild = ctx.guild

        linhas_ranking = []
        for user_id, registro in self.dados.items():
            membro = guild.get_member(int(user_id))
            if membro is None or membro.bot:
                continue
            pontos = pontos_do_periodo(registro)
            if pontos <= 0:
                continue
            linhas_ranking.append((membro, pontos))

        if not linhas_ranking:
            await ctx.send("📊 Ainda ninguém pontuou neste período.")
            return

        linhas_ranking.sort(key=lambda t: t[1], reverse=True)

        medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
        linhas = []
        for i, (membro, pontos) in enumerate(linhas_ranking[:25], start=1):
            prefixo = medalhas.get(i, f"**{i}.**")
            marcador_meta = " ✅" if pontos > META_PONTOS else ""
            linhas.append(f"{prefixo} {membro.mention} — **{pontos}**/{META_PONTOS} pts{marcador_meta}")

        embed = discord.Embed(
            title="📊 Ranking do Período Atual",
            description="\n".join(linhas),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text=(
                f"Esses pontos zeram quando o período reiniciar • "
                f"Período: {INICIO_PERIODO.strftime('%d/%m/%Y')} até {FIM_PERIODO.strftime('%d/%m/%Y')} "
                f"(meta: {META_PONTOS} pts)"
            )
        )
        await ctx.send(embed=embed)

    @periodo_pontuacao.error
    async def periodo_pontuacao_error(self, ctx, error):
        await ctx.send(f"❌ Erro ao usar o comando: {error}", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Atividade(bot))
