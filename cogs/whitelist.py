import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote

from cogs.backup import ler, salvar
from cogs.players import CARGOS as PLAYER_CARGOS, aplicar_cargo_rank, CARGO_GERAL_SEM_DIVISAO_IDS
from cogs.players import RANK_TIERS_ORDEM, RANK_TIERS_COM_DIVISAO, RANK_TIER_EMOJIS
from cogs import mod_utils as mu
from cogs.whitelist_extras import (
    CARGO_STAFF_WHITELIST_ID,
    buscar_historico,
    texto_aviso_historico,
    registrar_decisao,
    registrar_punicao_historico,
    preencher_stats_se_vazio,
)


CARGO_RANKS = {c["nome"]: c["id"] for c in PLAYER_CARGOS if c["secao"] == "rank"}

# divisões possíveis pra quem escolhe um rank com divisão (todo mundo, menos SSL)
RANK_DIVISOES_OPCOES = ["1", "2", "3"]


INCENTIVO_ESPERA_INICIAL_SEGUNDOS = 15 * 60
INCENTIVO_INTERVALO_MIN = 10
INCENTIVO_INTERVALO_MAX = 15


WHITELIST_TIMEOUT_DIAS = 3
WHITELIST_TIMEOUT_SEGUNDOS = WHITELIST_TIMEOUT_DIAS * 24 * 60 * 60


INCENTIVO_NAO_COMECOU = [
    "{mention} bora começar? 👀",
    "{mention} tá esperando o quê pra começar a whitelist? 🚀",
    "Ei {mention}, sua whitelist tá esperando você aqui! Bora começar? 😄",
    "{mention} vem logo, é rapidinho! Bora começar a whitelist? 🙌",
    "{mention} cadê você? Bora dar o start na whitelist! 💬",
    "Psst {mention}... a whitelist não vai se responder sozinha, bora começar? 😅",
    "{mention} só faltam alguns cliques pra você entrar de vez! Começa aí! 🎮",
    "{mention} bora lá, não deixa isso esfriar! Começa a whitelist! 🔥",
    "E aí {mention}, vamos começar a whitelist? Tá bem rápido! ⏱️",
    "{mention} ainda dá tempo, bora começar sua whitelist agora! ✅",
    "{mention} tá fazendo o quê que não começa a whitelist? Bora! 😄",
    "{mention} a whitelist tá aberta esperando você, só clicar aí! 🎯",
    "Oi {mention}, vamos começar? A whitelist é rapidinha! ⚡",
    "{mention} sua vaga tá te esperando, começa a whitelist logo! 🎟️",
    "{mention} bora, não deixa passar essa oportunidade! Começa a whitelist! 🏁",
    "E aí {mention}, esqueceu de começar a whitelist? Vem aqui! 🤔",
    "{mention} tá difícil clicar num botão? Bora começar a whitelist! 😂",
    "{mention} sua whitelist tá com ciúmes de você, vem dar atenção pra ela! 💌",
    "{mention} não enrola não, vem começar a whitelist de uma vez! 🚦",
    "{mention} bora logo, o servidor tá na torcida por você! 📣",
    "{mention} isso aqui não morde, pode começar a whitelist sem medo! 😅",
    "{mention} respondendo rápido você já tá dentro, bora começar! 🔓",
    "{mention} eu sei que você tá vendo essa mensagem, começa logo! 👁️",
    "{mention} vamos nessa? Sua whitelist não vai se preencher sozinha! 📋",
]


INCENTIVO_PAROU_NO_MEIO = [
    "{mention} bora acabar? Você já começou, falta pouco! 💪",
    "{mention} não para no meio não, vem terminar a whitelist! 🏁",
    "Ei {mention}, você tava indo bem! Bora acabar a whitelist? 👀",
    "{mention} falta só um pouquinho, vem finalizar! 🚀",
    "{mention} volta aí e termina sua whitelist, já foi metade do caminho! 🙌",
    "{mention} não desiste agora, a reta final tá logo ali! 🏆",
    "{mention} cadê você? Volta pra terminar sua whitelist! 🔍",
    "{mention} já passou da metade, não vai parar bem aqui não! 😤",
    "{mention} termina isso hoje, depois você me agradece! ✅",
    "{mention} tá quase lá, só faltam algumas perguntinhas! 📝",
    "{mention} deu uma pausa? Bora voltar e fechar a whitelist! ⏸️➡️▶️",
    "{mention} sua whitelist ficou pela metade, vem completar! 🧩",
    "{mention} não deixa esfriar, volta e termina agora! 🔥",
    "{mention} tá tão perto do fim, vem finalizar de uma vez! 🎯",
    "{mention} o servidor já quase te aprovou, só falta você terminar! 🙏",
]


CATEGORIA_WHITELIST_ID = 0
NOME_CATEGORIA_WHITELIST = "🔒 Whitelist"


CANAL_LOG_WHITELIST_ID = 1521897698419019907


STATUS_WHITELIST_CHANNEL_ID = 0
NOME_CANAL_STATUS = "status-whitelist"

STATUS_LABELS = {
    "pendente":    ("⏳ Pendente",   0xFEE75C),
    "visualizada": ("👀 Em análise", 0x5865F2),
    "aprovada":    ("✅ Aprovada",   0x57F287),
    "recusada":    ("❌ Recusada",   0xED4245),
    "cancelada":   ("🚫 Cancelada",  0x99AAB5),
}


CARGO_MEMBRO_EQUIPE_ID = 1532184563491541164


CARGO_MEMBRO_ID = 1523830313141272586


CARGO_IDIOMA_INGLES_ID = 1525312330831892481

PEAK_CONTAS = ["Nesta conta", "Em outra conta"]

IDIOMAS = ["Português", "Inglês"]
IDIOMA_EMOJIS = {"Português": "🇧🇷", "Inglês": "🇬🇧"}


CARGO_SEM_ACESSO_ID = 1521890714873757707


CARGOS_EXCLUIDOS_DA_TAG_STAFF = {
    1513240072139309317,
    1513356584946896946,
}

STAFF_ROLE_IDS = ({c["id"] for c in PLAYER_CARGOS if c["secao"] == "staff"} | {
    1511894837790769204,
    1523835085475020932,
    1523835045872275566,
    1523835010795176027,
    1523833330175442954,
    1523843469016043600,
}) - CARGOS_EXCLUIDOS_DA_TAG_STAFF


# Cargo com ACESSO TOTAL às whitelists: vê os canais, aprova, recusa, marca
# como em análise, fecha, consulta/edita perfil. Também é o cargo que o
# candidato "chama" no botão 🔔 Chamar Staff.

CARGOS_QUE_VEEM_WHITELIST = {
    1511895253777649704,
    1511894837790769204,
    1523835085475020932,
    CARGO_STAFF_WHITELIST_ID,
}

# Cargo de plataforma dado quando a whitelist é aprovada (Switch não tem cargo)
CARGOS_PLATAFORMA_IDS = {
    "PC":          1550986131858788523,
    "Xbox":        1550986187106287616,
    "PlayStation": 1544318397830004767,
}

# tempo mínimo entre dois "🔔 Chamar Staff" no mesmo canal (evita spam de ping)
CHAMAR_STAFF_COOLDOWN_SEGUNDOS = 5 * 60

# whitelist enviada e NINGUÉM da staff respondeu: o bot marca o cargo da staff da
# whitelist (CARGO_STAFF_WHITELIST_ID) depois de AVISO_STAFF_PRIMEIRO_SEGUNDOS e
# repete a cada AVISO_STAFF_INTERVALO_SEGUNDOS, até alguém da staff pegar a análise
# (botão Visualizada), decidir (aprovar/recusar) ou escrever no canal do candidato.
AVISO_STAFF_PRIMEIRO_SEGUNDOS = 5 * 60
AVISO_STAFF_INTERVALO_SEGUNDOS = 30 * 60

RANK_IDS = set(CARGO_RANKS.values())

PLATAFORMAS = ["PC", "Xbox", "PlayStation", "Switch"]

PEAK_RANKS = [
    "Bronze", "Prata", "Ouro", "Platina",
    "Diamante", "Champion", "Grand Champion", "Supersonic Legend",
]
DIVISOES = ["Divisão 1", "Divisão 2", "Divisão 3"]

TEMPOS_JOGANDO = ["Menos de 1 ano", "1 a 2 anos", "2 a 4 anos", "Mais de 4 anos"]


HABILIDADES = ["Programação", "Designer", "Roteiro", "Editor de vídeo", "Administração"]


# plataforma da whitelist -> nome usado na URL do Rocket League Tracker.
# PC cai em "epic" (a maioria joga pela Epic); se o perfil for Steam, é só trocar
# "epic" por "steam" na URL aberta.
TRACKER_PLATAFORMAS = {
    "PC": "epic",
    "Xbox": "xbl",
    "PlayStation": "psn",
    "Switch": "switch",
}


def url_tracker(respostas: dict | None) -> str | None:
    """Link do perfil no Rocket League Tracker (nick + plataforma da whitelist)."""
    r = respostas or {}
    nick = (r.get("nick") or "").strip()
    plat = TRACKER_PLATAFORMAS.get(r.get("plataforma", ""))
    if not nick or nick == "—" or not plat:
        return None
    return f"https://rocketleague.tracker.network/rocket-league/profile/{plat}/{quote(nick, safe='')}/overview"


def _pode_gerir(membro) -> bool:
    """Quem pode mexer em whitelists: dono do bot, administradores e quem tem
    o cargo da whitelist (CARGO_STAFF_WHITELIST_ID)."""
    if mu.eh_super_admin(membro.id):
        return True
    perms = getattr(membro, "guild_permissions", None)
    if perms is not None and perms.administrator:
        return True
    return any(r.id == CARGO_STAFF_WHITELIST_ID for r in getattr(membro, "roles", []))


def _ctx_pode_gerir(ctx: commands.Context) -> bool:
    return ctx.guild is not None and _pode_gerir(ctx.author)


def _inter_pode_gerir(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None and _pode_gerir(interaction.user)


def _inter_pode_ver_perfil(interaction: discord.Interaction) -> bool:
    if not _inter_pode_gerir(interaction):
        return any(r.id == CARGO_MEMBRO_EQUIPE_ID for r in getattr(interaction.user, "roles", []))
    return True


async def _travar_mensagem(interaction: discord.Interaction) -> None:
    """Tira os componentes da mensagem da pergunta depois que a pessoa
    respondeu — sem isso dava pra responder duas vezes e a próxima pergunta
    era enviada duplicada."""
    try:
        if interaction.message is not None:
            await interaction.message.edit(view=None)
    except discord.HTTPException:
        pass


async def _responder(interaction: discord.Interaction, texto: str, **kw) -> None:
    """Responde o clique SEM nunca estourar: se a interação já tiver expirado
    (o Discord só dá 3s pra responder), manda no canal mesmo assim — a pessoa não
    fica sem retorno e o fluxo continua."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(texto, **kw)
        else:
            await interaction.response.send_message(texto, **kw)
    except discord.HTTPException:
        if kw.get("ephemeral") or interaction.channel is None:
            return
        try:
            await interaction.channel.send(texto)
        except discord.HTTPException:
            pass


MSG_ERRO_ETAPA = (
    "⚠️ Algo deu errado aqui. Clique em **🔄 Refazer pergunta** (primeira mensagem do canal) "
    "ou use `/retomar_whitelist` pra continuar de onde parou."
)


def _log_erro(onde: str, error: BaseException) -> None:
    import traceback
    print(f"[WHITELIST] ❌ Erro em {onde}: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


class _ViewComErro(discord.ui.View):
    """Qualquer erro num botão/menu da whitelist vira aviso pra pessoa (antes ela só
    via 'interação falhou' e o bot parecia travado), além de ir pro console."""

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        _log_erro(f"{type(self).__name__}/{getattr(item, 'custom_id', '?')}", error)
        await _responder(interaction, MSG_ERRO_ETAPA, ephemeral=True)


def _slug(nome: str) -> str:
    # tira os acentos antes de limpar: "João" virava "jo-o", agora vira "joao"
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = nome.lower().strip()
    nome = re.sub(r"[^a-z0-9\-]+", "-", nome)
    nome = re.sub(r"-+", "-", nome).strip("-")
    return nome or "jogador"


class NickModal(discord.ui.Modal, title="Whitelist — Nick no Rocket League"):
    nick = discord.ui.TextInput(
        label="Qual seu nick no Rocket League?",
        placeholder="Ex: Squishy",
        max_length=32,
        required=True,
    )

    def __init__(self, cog: "Whitelist"):
        super().__init__()
        self.cog = cog

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        _log_erro("NickModal", error)
        await _responder(interaction, MSG_ERRO_ETAPA, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        cog = self.cog
        nick_valor = " ".join(self.nick.value.split())  # tira espaços repetidos e quebras de linha

        registro = cog.dados.get(str(membro.id))
        if registro is None or registro.get("status") != "em_andamento":
            await interaction.response.send_message("⚠️ Não dá mais pra mexer nessa whitelist.", ephemeral=True)
            return
        if not nick_valor:
            await interaction.response.send_message("⚠️ Escreva o seu nick no Rocket League. Clica em **Começar** de novo.", ephemeral=True)
            return

        async with cog.trava(membro.id):
            if registro.get("respostas", {}).get("nick"):
                await interaction.response.send_message(
                    "⚠️ Você já registrou seu nick — siga as perguntas abaixo (se travou, clique em **🔄 Refazer pergunta**).",
                    ephemeral=True,
                )
                return
            # confirma o clique ANTES de qualquer coisa lenta (o Discord só espera 3s)
            await interaction.response.defer()
            cog.salvar_resposta(membro.id, "nick", nick_valor)

            aviso_nick = ""
            try:
                await membro.edit(nick=nick_valor, reason="Whitelist — nick informado")
            except discord.Forbidden:
                aviso_nick = "\n⚠️ Não consegui atualizar seu apelido (permissão), mas seguimos!"
            except discord.HTTPException:
                aviso_nick = "\n⚠️ Não consegui atualizar seu apelido, mas seguimos!"

            await _responder(interaction, f"✅ Nick registrado: **{nick_valor}**{aviso_nick}")
            await cog.enviar_pergunta(interaction.channel, membro, "idioma")


def normalizar_tiktok(texto: str) -> tuple[str | None, str | None]:
    """Aceita só o usuário ("seuusuario" / "@seuusuario") ou o link completo.
    Devolve (valor_pra_salvar, erro). O valor salvo é sempre o link do perfil,
    pra continuar clicável nos resumos (e igual ao que já existia salvo)."""
    t = (texto or "").strip().strip("<>").strip()
    if not t:
        return None, "Escreva seu usuário do TikTok (ex: @seuusuario)."
    if "tiktok.com" in t.lower():
        m = re.search(r"tiktok\.com/@([A-Za-z0-9_.]+)", t, re.IGNORECASE)
        if m:
            usuario = m.group(1)
        elif re.match(r"https?://(?:[\w-]+\.)?tiktok\.com/\S+$", t, re.IGNORECASE):
            return t[:200], None  # link curto (vm.tiktok.com/...): não dá pra tirar o @, mantém
        else:
            return None, "Não entendi esse link. Escreva só o seu usuário (ex: @seuusuario)."
    else:
        usuario = t[1:] if t.startswith("@") else t  # só UM @ na frente; "@@x" e "@ x" não valem
    if not re.fullmatch(r"[A-Za-z0-9_.]{2,24}", usuario):
        return None, "Usuário inválido. Use só letras, números, _ e . (ex: @seuusuario)."
    return f"https://www.tiktok.com/@{usuario}", None


class PerguntasAbertasModal(discord.ui.Modal, title="Whitelist — Perguntas"):
    # pra add uma pergunta nova de texto livre é só criar outro TextInput
    # aqui embaixo, tipo o do tiktok, só troca label/placeholder/max_length
    # modal aceita até 5 campos, então dá de sobra
    tiktok = discord.ui.TextInput(
        label="Qual o seu usuário do TikTok?",
        placeholder="Ex: @seuusuario (pode colocar o link também)",
        style=discord.TextStyle.short,
        max_length=200,
        required=True,
    )

    def __init__(self, cog: "Whitelist"):
        super().__init__()
        self.cog = cog

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        _log_erro("PerguntasAbertasModal", error)
        await _responder(interaction, MSG_ERRO_ETAPA, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        cog = self.cog
        registro = cog.dados.get(str(membro.id))
        if registro is None or registro.get("status") != "em_andamento":
            await interaction.response.send_message("⚠️ Sua whitelist já foi enviada pra análise.", ephemeral=True)
            return
        valor, erro = normalizar_tiktok(self.tiktok.value)
        if erro:
            await interaction.response.send_message(f"⚠️ {erro} Clica em **Responder Perguntas** e tenta de novo.", ephemeral=True)
            return

        async with cog.trava(membro.id):
            etapa = registro.get("etapa_atual")
            ja_respondeu = (etapa is not None and etapa != "perguntas_abertas") or (
                etapa is None and registro.get("respostas", {}).get("tiktok")
            )
            if ja_respondeu:
                await interaction.response.send_message("⚠️ Você já respondeu essa pergunta.", ephemeral=True)
                return
            await interaction.response.defer()
            cog.salvar_resposta(membro.id, "tiktok", valor)
            # e aqui salva a resposta do campo novo, mesma ideia, só troca a
            # chave (o nome que fica salvo no json, tipo "tiktok") e o valor
            # pra pegar do campo que vc criou lá em cima
            await _travar_mensagem(interaction)
            await _responder(interaction, "✅ Respostas registradas!")
            await cog.enviar_pergunta(interaction.channel, membro, "duvidas")


class DesistirButton(discord.ui.Button):
    """Botão reutilizável de 'desistir', adicionado nas etapas intermediárias
    da whitelist (depois da primeira tela) pra pessoa poder desistir a
    qualquer momento, não só no início."""
    def __init__(self):
        super().__init__(label="🚫 Desistir", style=discord.ButtonStyle.secondary, custom_id="wl_desistir_etapa", row=4)

    async def callback(self, interaction: discord.Interaction):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.pedir_confirmacao_desistencia(interaction)


class AbrirPerguntasView(_ViewComErro):
    def __init__(self, cog: "Whitelist"):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(DesistirButton())

    @discord.ui.button(label="📝 Responder Perguntas", style=discord.ButtonStyle.primary, custom_id="wl_perguntas_abertas")
    async def responder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.checar_dono(interaction):
            return
        await interaction.response.send_modal(PerguntasAbertasModal(self.cog))


class EscolhaSelect(discord.ui.Select):
    def __init__(self, cog: "Whitelist", step: str, opcoes: list[str], placeholder: str, prox_step: str | None, emojis: dict | None = None):
        options = [
            discord.SelectOption(label=o, emoji=(emojis or {}).get(o))
            for o in opcoes
        ]
        # custom_id fixo por etapa: assim o menu continua funcionando depois que
        # o bot reinicia (antes ele ficava "interação falhou" pra quem estava no meio)
        super().__init__(placeholder=placeholder, options=options, custom_id=f"wl_sel_{step}")
        self.cog = cog
        self.step = step
        self.prox_step = prox_step

    async def callback(self, interaction: discord.Interaction):
        cog = self.cog
        if not await cog.checar_dono(interaction):
            return
        membro = interaction.user
        # um clique de cada vez por pessoa: clique duplo não duplica a próxima pergunta
        async with cog.trava(membro.id):
            if not cog.etapa_valida(membro.id, self.step):
                await interaction.response.send_message(
                    "⚠️ Essa pergunta já foi respondida (ou não é a atual). Se travou, clique em **🔄 Refazer pergunta**.",
                    ephemeral=True,
                )
                await _travar_mensagem(interaction)
                return
            # 1º: confirma o clique (o Discord só espera 3s). Antes o bot editava a mensagem
            # e trocava cargos ANTES de responder: se demorasse, a resposta falhava, a
            # pergunta ficava travada e a próxima nunca vinha. Foi isso que deixou a pessoa
            # presa na pergunta do microfone.
            await interaction.response.defer()
            await _travar_mensagem(interaction)
            await cog.processar_escolha(interaction, self.step, self.values[0], self.prox_step)


class EscolhaView(_ViewComErro):
    def __init__(self, cog: "Whitelist", step: str, opcoes: list[str], placeholder: str, prox_step: str | None, emojis: dict | None = None):
        super().__init__(timeout=None)
        self.add_item(EscolhaSelect(cog, step, opcoes, placeholder, prox_step, emojis))
        self.add_item(DesistirButton())


class HabilidadesSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=h) for h in HABILIDADES]
        super().__init__(
            placeholder="Escolha uma ou mais habilidades (opcional)...",
            options=options,
            min_values=1,
            max_values=len(options),
            custom_id="wl_sel_habilidades",
        )

    async def callback(self, interaction: discord.Interaction):
        cog: "Whitelist" = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        membro = interaction.user
        async with cog.trava(membro.id):
            if not cog.etapa_valida(membro.id, "habilidades"):
                await interaction.response.send_message(
                    "⚠️ Essa pergunta já foi respondida (ou não é a atual). Se travou, clique em **🔄 Refazer pergunta**.",
                    ephemeral=True,
                )
                await _travar_mensagem(interaction)
                return
            await interaction.response.defer()
            await _travar_mensagem(interaction)
            valor = ", ".join(self.values)
            cog.salvar_resposta(membro.id, "habilidades", valor)
            await _responder(interaction, f"✅ Habilidade(s) registrada(s): **{valor}**")
            await cog.prosseguir_apos_habilidades(interaction.channel, membro)


class HabilidadesView(_ViewComErro):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HabilidadesSelect())
        self.add_item(DesistirButton())

    @discord.ui.button(label="⏭️ Pular", style=discord.ButtonStyle.secondary, custom_id="wl_pular_habilidades", row=1)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: "Whitelist" = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        membro = interaction.user
        async with cog.trava(membro.id):
            if not cog.etapa_valida(membro.id, "habilidades"):
                await interaction.response.send_message(
                    "⚠️ Essa pergunta já foi respondida (ou não é a atual). Se travou, clique em **🔄 Refazer pergunta**.",
                    ephemeral=True,
                )
                await _travar_mensagem(interaction)
                return
            await interaction.response.defer()
            await _travar_mensagem(interaction)
            cog.salvar_resposta(membro.id, "habilidades", "Nenhuma")
            await _responder(interaction, "⏭️ Pergunta pulada — nenhuma habilidade registrada.")
            await cog.prosseguir_apos_habilidades(interaction.channel, membro)


class ComecarWhitelistView(_ViewComErro):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚀 Começar Whitelist", style=discord.ButtonStyle.success, custom_id="wl_comecar")
    async def comecar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        if cog.dados.get(str(interaction.user.id), {}).get("respostas", {}).get("nick"):
            # já começou: em vez de só avisar, reenvia a pergunta em que parou
            await interaction.response.defer(ephemeral=True)
            texto = await cog.reenviar_etapa(interaction.channel, interaction.user)
            await interaction.followup.send(texto, ephemeral=True)
            return
        await interaction.response.send_modal(NickModal(cog))

    @discord.ui.button(label="🔄 Refazer pergunta", style=discord.ButtonStyle.secondary, custom_id="wl_retomar")
    async def retomar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Travou ou fechou a aba sem responder? Reenvia a pergunta em que parou."""
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        texto = await cog.reenviar_etapa(interaction.channel, interaction.user)
        await interaction.followup.send(texto, ephemeral=True)

    @discord.ui.button(label="🚫 Desistir", style=discord.ButtonStyle.secondary, custom_id="wl_desistir")
    async def desistir(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.pedir_confirmacao_desistencia(interaction)

    @discord.ui.button(label="🗑️ Cancelar/Fechar (staff)", style=discord.ButtonStyle.danger, custom_id="wl_cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cargos = {r.id for r in interaction.user.roles}
        if not (_pode_gerir(interaction.user) or cargos & CARGOS_QUE_VEEM_WHITELIST):
            await interaction.response.send_message("❌ Apenas staff pode fechar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        # whitelist em análise por um manager: só ele pode fechar o canal
        registro_canal = next(
            (r for r in cog.dados.values() if r.get("canal_id") == interaction.channel.id), None
        )
        bloqueio = cog._bloqueio_analise(registro_canal, interaction.user.id)
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return
        cog.marcar_cancelada(interaction.channel.id, motivo="staff")
        await interaction.response.send_message("🔒 Fechando canal em 3 segundos...")
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Whitelist cancelada por {interaction.user}")

    @discord.ui.button(label="🔔 Chamar Staff", style=discord.ButtonStyle.primary, custom_id="wl_chamar_staff")
    async def chamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.chamar_staff(interaction)


class ConfirmarDesistenciaView(discord.ui.View):
    """Confirmação antes de fechar o canal pra evitar clique acidental."""
    def __init__(self, membro_id: int):
        super().__init__(timeout=60)
        self.membro_id = membro_id

    @discord.ui.button(label="✅ Sim, desistir", style=discord.ButtonStyle.danger, custom_id="wl_desistir_confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.confirmar_desistencia(interaction, self.membro_id)

    @discord.ui.button(label="↩️ Voltar", style=discord.ButtonStyle.secondary, custom_id="wl_desistir_voltar")
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Beleza, sua whitelist continua normalmente! 👍", view=None)


class FinalizarWhitelistView(_ViewComErro):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Concluir Whitelist", style=discord.ButtonStyle.success, custom_id="wl_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.solicitar_aprovacao(interaction)

    @discord.ui.button(label="🔔 Chamar Staff", style=discord.ButtonStyle.primary, custom_id="wl_chamar_staff_final")
    async def chamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.chamar_staff(interaction)


def _checar_admin(interaction: discord.Interaction) -> bool:
    return _pode_gerir(interaction.user)


class ConfirmarDecisaoView(discord.ui.View):
    """Confirmação antes de APROVAR (quando a pessoa já foi expulsa/banida) ou
    de RECUSAR (que expulsa o membro). Só quem pediu a ação pode confirmar."""
    def __init__(self, membro_id: int, autor_id: int, aprovar: bool, forcar_publico: bool = False):
        super().__init__(timeout=120)
        self.membro_id = membro_id
        self.autor_id = autor_id
        self.aprovar = aprovar
        self.forcar_publico = forcar_publico
        self.message: discord.Message | None = None
        self.interaction: discord.Interaction | None = None
        self.confirmar.label = "✅ Sim, aceitar mesmo assim" if aprovar else "✅ Sim, recusar"
        self.confirmar.style = discord.ButtonStyle.success if aprovar else discord.ButtonStyle.danger

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Só quem pediu essa ação pode confirmar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="⏳ Processando...", view=None)
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        erro, mensagem = await cog.decidir(interaction.guild, self.membro_id, interaction.user, self.aprovar)
        if erro:
            await interaction.edit_original_response(content=mensagem)
        else:
            await interaction.edit_original_response(
                content="✅ Whitelist aprovada!" if self.aprovar else "✅ Whitelist recusada!"
            )

    @discord.ui.button(label="↩️ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Beleza, nada foi feito. A whitelist continua como estava. 👍", view=None)

    async def on_timeout(self):
        try:
            texto = "⌛ Confirmação expirada — nada foi feito."
            if self.interaction is not None:
                await self.interaction.edit_original_response(content=texto, view=None)
            elif self.message is not None:
                await self.message.edit(content=texto, view=None)
        except discord.HTTPException:
            pass


# ── edição das respostas pela staff (antes de aprovar) ─────────────────────
# chave da resposta -> (rótulo, tipo, extra)
#   tipo "texto"   -> abre um modal (extra = tamanho máximo)
#   tipo "escolha" -> menu de uma opção (extra = lista de opções)
#   tipo "multi"   -> menu de várias opções
# pergunta nova na whitelist? é só adicionar a linha aqui também
CAMPOS_EDITAVEIS = {
    "nick":        ("Nick RL", "texto", 32),
    "idioma":      ("Idioma", "escolha", IDIOMAS),
    "rank":        ("Rank atual", "escolha", None),
    "plataforma":  ("Plataforma", "escolha", PLATAFORMAS),
    "peak_rank":   ("Maior rank", "escolha", PEAK_RANKS),
    "peak_div":    ("Divisão do maior rank", "escolha", DIVISOES),
    "peak_conta":  ("Conta do maior rank", "escolha", PEAK_CONTAS),
    "tempo":       ("Tempo jogando", "escolha", TEMPOS_JOGANDO),
    "microfone":   ("Microfone", "escolha", ["Sim", "Não"]),
    "ativo":       ("Ativo?", "escolha", ["Sim", "Não"]),
    "tem_tiktok":  ("Tem TikTok?", "escolha", ["Sim", "Não"]),
    "tiktok":      ("TikTok (usuário ou link)", "texto", 200),
    "habilidades": ("Habilidades", "multi", None),
}


def _limpo(valor, limite: int = 100) -> str:
    """Texto seguro pra jogar numa mensagem: sem menção e sem markdown solto."""
    texto = discord.utils.escape_mentions(discord.utils.escape_markdown(str(valor)))
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _opcoes_campo(chave: str) -> list[str]:
    if chave == "rank":
        # mesmo formato que o fluxo normal grava: "Champion 2", "Super Sonic Legend"
        opcoes = []
        for tier in RANK_TIERS_ORDEM:
            if tier in RANK_TIERS_COM_DIVISAO:
                opcoes += [f"{tier} {d}" for d in RANK_DIVISOES_OPCOES]
            else:
                opcoes.append(tier)
        return opcoes
    if chave == "habilidades":
        return HABILIDADES + ["Nenhuma"]
    return CAMPOS_EDITAVEIS[chave][2]


class _ViewEdicao(discord.ui.View):
    """Base dos menus efêmeros de edição: só quem clicou em ✏️ mexe neles."""

    def __init__(self, cog: "Whitelist", membro_id: int, autor_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.membro_id = membro_id
        self.autor_id = autor_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Esse menu é de quem abriu a edição.", ephemeral=True)
            return False
        return True


class CampoSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=rotulo, value=chave) for chave, (rotulo, _, _) in CAMPOS_EDITAVEIS.items()]
        super().__init__(placeholder="Qual resposta você quer corrigir?", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: "EditarCampoView" = self.view
        chave = self.values[0]
        rotulo, tipo, _ = CAMPOS_EDITAVEIS[chave]
        if tipo == "texto":
            atual = view.cog.dados.get(str(view.membro_id), {}).get("respostas", {}).get(chave, "")
            await interaction.response.send_modal(EditarTextoModal(view.cog, view.membro_id, chave, atual))
            return
        await interaction.response.edit_message(
            content=f"Escolha o novo valor de **{rotulo}**:",
            embed=None,
            view=EscolherValorView(view.cog, view.membro_id, view.autor_id, chave),
        )


class EditarCampoView(_ViewEdicao):
    def __init__(self, cog: "Whitelist", membro_id: int, autor_id: int):
        super().__init__(cog, membro_id, autor_id)
        self.add_item(CampoSelect())


class ValorSelect(discord.ui.Select):
    def __init__(self, chave: str):
        opcoes = _opcoes_campo(chave)
        multi = CAMPOS_EDITAVEIS[chave][1] == "multi"
        super().__init__(
            placeholder="Escolha o novo valor..." if not multi else "Escolha uma ou mais opções...",
            options=[discord.SelectOption(label=o) for o in opcoes],
            min_values=1,
            max_values=len(opcoes) if multi else 1,
        )
        self.chave = chave

    async def callback(self, interaction: discord.Interaction):
        view: "EscolherValorView" = self.view
        if "Nenhuma" in self.values:
            valor = "Nenhuma"
        else:
            valor = ", ".join(self.values)
        # editar mexe em apelido/cargo/mensagens e pode passar dos 3s do Discord: confirma o clique primeiro
        await interaction.response.defer()
        _, texto = await view.cog.aplicar_edicao(interaction.guild, interaction.user, view.membro_id, self.chave, valor)
        # volta pro menu de campos, já mostrando as respostas atualizadas
        await interaction.edit_original_response(
            content=texto,
            embed=view.cog._embed_edicao(interaction.guild, view.membro_id),
            view=EditarCampoView(view.cog, view.membro_id, view.autor_id),
        )


class EscolherValorView(_ViewEdicao):
    def __init__(self, cog: "Whitelist", membro_id: int, autor_id: int, chave: str):
        super().__init__(cog, membro_id, autor_id)
        self.add_item(ValorSelect(chave))

    @discord.ui.button(label="↩️ Voltar", style=discord.ButtonStyle.secondary, row=1)
    async def voltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=self.cog._embed_edicao(interaction.guild, self.membro_id),
            view=EditarCampoView(self.cog, self.membro_id, self.autor_id),
        )


class EditarTextoModal(discord.ui.Modal):
    def __init__(self, cog: "Whitelist", membro_id: int, chave: str, atual: str):
        rotulo, _, limite = CAMPOS_EDITAVEIS[chave]
        super().__init__(title=f"Editar — {rotulo}"[:45])
        self.cog = cog
        self.membro_id = membro_id
        self.chave = chave
        self.valor = discord.ui.TextInput(
            label=rotulo[:45],
            default=("" if atual in (None, "—") else str(atual))[:limite],
            max_length=limite,
            required=True,
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        _, texto = await self.cog.aplicar_edicao(
            interaction.guild, interaction.user, self.membro_id, self.chave, self.valor.value.strip()
        )
        await interaction.followup.send(texto, ephemeral=True)


class RevisaoWhitelistView(discord.ui.View):
    """Botões de revisão (Visualizada / Aprovar / Recusar), mais 💬 Abrir/Fechar chat
    e ✏️ Editar respostas (+ link 📂 pro canal, no log).

    IMPORTANTE: quem é o candidato NÃO fica guardado aqui. Os botões são
    persistentes (todos usam o mesmo custom_id) e, depois de um restart, o
    Discord entrega o clique pra uma única instância registrada — então o
    candidato é descoberto na hora do clique, pela mensagem ou pelo canal
    (ver Whitelist.membro_id_da_interacao). Antes isso aprovava/recusava a
    pessoa errada quando havia mais de uma whitelist pendente.

    Passando guild_id e canal_id aparece o botão 📂 que abre o chat da
    whitelist (usado na mensagem do canal de log)."""
    def __init__(self, guild_id: int | None = None, canal_id: int | None = None, tracker_url: str | None = None):
        super().__init__(timeout=None)
        if tracker_url:
            self.add_item(discord.ui.Button(
                label="📊 Ver no Tracker",
                style=discord.ButtonStyle.link,
                url=tracker_url,
                row=1,
            ))
        if guild_id and canal_id and canal_id > 0:
            self.add_item(discord.ui.Button(
                label="📂 Abrir chat da whitelist",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild_id}/{canal_id}",
                row=1,
            ))

    @discord.ui.button(label="👀 Marcar como Visualizada", style=discord.ButtonStyle.secondary, custom_id="wl_visualizar")
    async def visualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só a staff da whitelist pode revisar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.marcar_visualizada(interaction)

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success, custom_id="wl_aprovar")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só a staff da whitelist pode revisar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.iniciar_decisao(interaction, aprovar=True)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger, custom_id="wl_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só a staff da whitelist pode revisar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.iniciar_decisao(interaction, aprovar=False)

    @discord.ui.button(label="💬 Abrir/Fechar chat", style=discord.ButtonStyle.primary, custom_id="wl_chat_toggle", row=1)
    async def chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só a staff da whitelist pode usar isso.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.alternar_chat(interaction)

    @discord.ui.button(label="✏️ Editar respostas", style=discord.ButtonStyle.secondary, custom_id="wl_editar", row=1)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só a staff da whitelist pode editar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.abrir_edicao(interaction)


class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("whitelist")
        preencher_stats_se_vazio(self.dados)
        self.limpeza_canais.start()
        self.incentivo_whitelist.start()
        self._locks: dict[int, asyncio.Lock] = {}
        self.lembrar_staff_whitelist.start()
        self.retomar_etapas_whitelist.start()

    async def cog_load(self):
        """Registra TODAS as views persistentes da whitelist (antes só 3 eram
        registradas, e os menus de pergunta morriam quando o bot reiniciava)."""
        self.bot.add_view(ComecarWhitelistView())
        self.bot.add_view(FinalizarWhitelistView())
        self.bot.add_view(RevisaoWhitelistView())
        self.bot.add_view(HabilidadesView())
        self.bot.add_view(AbrirPerguntasView(self))
        for step in self._config_escolha():
            self.bot.add_view(self._view_escolha(step))

    def cog_unload(self):
        self.limpeza_canais.cancel()
        self.incentivo_whitelist.cancel()
        self.lembrar_staff_whitelist.cancel()
        self.retomar_etapas_whitelist.cancel()

    @tasks.loop(minutes=1)
    async def incentivo_whitelist(self):
        """Cobra (de forma chata mesmo, de propósito) quem não terminou a
        whitelist: manda mensagem no canal dele a cada 10-15 min, começando
        só 15 min depois do canal ter sido criado."""
        await self.bot.wait_until_ready()
        agora = time.time()
        mudou = False

        for uid_str, registro in list(self.dados.items()):
            if registro.get("status") != "em_andamento":
                continue

            canal_id = registro.get("canal_id")
            if not canal_id:
                continue

            criado_ts = registro.get("criado_ts")
            if not criado_ts:


                registro["criado_ts"] = agora
                mudou = True
                continue

            if agora - criado_ts < INCENTIVO_ESPERA_INICIAL_SEGUNDOS:
                continue


            if agora - criado_ts >= WHITELIST_TIMEOUT_SEGUNDOS:
                canal = self.bot.get_channel(canal_id)
                if canal is not None:
                    try:
                        dias = WHITELIST_TIMEOUT_SEGUNDOS // 86400
                        await canal.send(
                            f"⏰ Já se passaram **{dias} dias** e essa whitelist não foi concluída, "
                            f"então vou fechar este canal automaticamente. Se quiser tentar de novo, "
                            f"entre em contato com a staff. 👋"
                        )
                        await asyncio.sleep(5)
                        await canal.delete(reason="Whitelist expirada por timeout automático")
                    except discord.HTTPException:
                        pass
                registro["status"] = "cancelada"
                registro["cancelado_motivo"] = "timeout"
                registro["cancelado_em"] = agora
                mudou = True
                continue

            proximo_ts = registro.get("proximo_incentivo_ts")
            if not proximo_ts:
                registro["proximo_incentivo_ts"] = agora
                mudou = True
                proximo_ts = agora

            if agora < proximo_ts:
                continue

            canal = self.bot.get_channel(canal_id)
            if canal is None:
                registro["proximo_incentivo_ts"] = agora + random.randint(INCENTIVO_INTERVALO_MIN, INCENTIVO_INTERVALO_MAX) * 60
                mudou = True
                continue

            membro = canal.guild.get_member(int(uid_str))
            if membro is None:
                registro["proximo_incentivo_ts"] = agora + random.randint(INCENTIVO_INTERVALO_MIN, INCENTIVO_INTERVALO_MAX) * 60
                mudou = True
                continue

            ja_comecou = bool(registro.get("respostas"))
            lista = INCENTIVO_PAROU_NO_MEIO if ja_comecou else INCENTIVO_NAO_COMECOU
            mensagem = random.choice(lista).format(mention=membro.mention)

            try:
                await canal.send(mensagem)
            except discord.HTTPException:
                pass

            registro["proximo_incentivo_ts"] = agora + random.randint(INCENTIVO_INTERVALO_MIN, INCENTIVO_INTERVALO_MAX) * 60
            mudou = True

        if mudou:
            salvar("whitelist", self.dados)

    @incentivo_whitelist.before_loop
    async def antes_incentivo_whitelist(self):
        await self.bot.wait_until_ready()

    # ── cobrança da staff quando a whitelist fica sem resposta ─────────────
    @staticmethod
    def _texto_espera(segundos: float) -> str:
        minutos = max(1, int(segundos // 60))
        if minutos < 60:
            return f"{minutos} min"
        horas, resto = divmod(minutos, 60)
        return f"{horas}h" if resto == 0 else f"{horas}h{resto:02d}"

    @commands.Cog.listener("on_message")
    async def _staff_respondeu(self, message: discord.Message):
        """Staff da whitelist escreveu no canal de uma whitelist pendente = já
        está atendendo: o bot para de cobrar essa."""
        if message.guild is None or message.author.bot:
            return
        if not _pode_gerir(message.author):
            return
        membro_id = self._membro_id_do_canal(message.channel.id)
        if membro_id is None or membro_id == message.author.id:
            return
        registro = self.dados.get(str(membro_id))
        if not registro or registro.get("status") != "pendente":
            return
        registro["staff_respondeu_ts"] = time.time()
        salvar("whitelist", self.dados)

    @tasks.loop(minutes=1)
    async def lembrar_staff_whitelist(self):
        agora = time.time()
        mudou = False

        for uid_str, registro in list(self.dados.items()):
            if registro.get("status") != "pendente" or registro.get("canal_apagado"):
                continue
            canal_id = registro.get("canal_id")
            if not canal_id:
                continue

            enviado_ts = registro.get("enviado_ts")
            if not enviado_ts:
                # whitelist pendente de antes dessa função: começa a contar daqui
                registro["enviado_ts"] = agora
                mudou = True
                continue

            # staff já escreveu no canal depois do envio: está sendo atendida
            if registro.get("staff_respondeu_ts", 0) >= enviado_ts:
                continue

            ultimo = registro.get("ultimo_aviso_staff_ts", 0)
            if ultimo >= enviado_ts:
                if agora - ultimo < AVISO_STAFF_INTERVALO_SEGUNDOS:
                    continue
                primeiro_aviso = False
            else:
                if agora - enviado_ts < AVISO_STAFF_PRIMEIRO_SEGUNDOS:
                    continue
                primeiro_aviso = True

            canal = self.bot.get_channel(canal_id)
            if canal is None:
                continue
            cargo = canal.guild.get_role(CARGO_STAFF_WHITELIST_ID)
            if cargo is None:
                continue

            espera = self._texto_espera(agora - enviado_ts)
            dono = f"<@{uid_str}>"
            if primeiro_aviso:
                texto = f"⏰ {cargo.mention} — a whitelist de {dono} foi enviada há **{espera}** e ainda ninguém da staff respondeu!"
            else:
                texto = f"🔔 {cargo.mention} — a whitelist de {dono} continua esperando há **{espera}**. Alguém pode dar uma olhada?"

            await self._garantir_acesso_staff(canal)
            try:
                await canal.send(texto, allowed_mentions=discord.AllowedMentions(roles=[cargo], users=False, everyone=False))
            except discord.HTTPException as e:
                print(f"[WHITELIST] ⚠️ Não consegui marcar a staff em {canal_id}: {e}")

            # marca mesmo se falhou: tenta de novo só no próximo intervalo (sem spam de erro)
            registro["ultimo_aviso_staff_ts"] = agora
            mudou = True

        if mudou:
            salvar("whitelist", self.dados)

    @lembrar_staff_whitelist.before_loop
    async def antes_lembrar_staff_whitelist(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def limpeza_canais(self):
        await self.bot.wait_until_ready()
        agora = time.time()
        mudou = False
        for uid_str, registro in list(self.dados.items()):


            if registro.get("status") not in ("aprovada", "recusada") or registro.get("canal_apagado"):
                continue
            deletar_em = registro.get("deletar_em")
            if not deletar_em or agora < deletar_em:
                continue
            canal_id = registro.get("canal_id")
            canal = self.bot.get_channel(canal_id) if canal_id else None
            if canal:
                try:
                    await canal.delete(reason="Whitelist decidida — canal removido automaticamente após 10 minutos")
                except discord.HTTPException:
                    pass
            registro["canal_apagado"] = True
            mudou = True
        if mudou:
            salvar("whitelist", self.dados)

    @limpeza_canais.before_loop
    async def antes_limpeza(self):
        await self.bot.wait_until_ready()


    def salvar_resposta(self, user_id: int, chave: str, valor: str):
        # só atualiza whitelist que já existe — antes qualquer clique (ex.: de
        # um staff) criava um registro-fantasma "em_andamento" sem canal
        registro = self.dados.get(str(user_id))
        if registro is None:
            return
        registro.setdefault("respostas", {})[chave] = valor
        salvar("whitelist", self.dados)

    # ── quem está mexendo na whitelist? ────────────────────────────────────
    async def checar_dono(self, interaction: discord.Interaction, exigir_andamento: bool = True) -> bool:
        """Só o dono da whitelist (dono do canal) pode responder as perguntas.
        Antes, qualquer pessoa com acesso ao canal (staff) que clicasse nos
        botões gravava respostas no próprio nome e até trocava o próprio apelido."""
        dono_id = self._membro_id_do_canal(interaction.channel.id) if interaction.channel else None
        if dono_id is None:
            await interaction.response.send_message(
                "⚠️ Não achei os dados dessa whitelist. Chama a staff.", ephemeral=True
            )
            return False
        if dono_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Essa whitelist é de outra pessoa — só quem está fazendo ela pode responder.", ephemeral=True
            )
            return False
        if exigir_andamento and self.dados.get(str(dono_id), {}).get("status") != "em_andamento":
            await interaction.response.send_message(
                "⚠️ Sua whitelist já foi enviada pra análise — não dá mais pra mudar as respostas.", ephemeral=True
            )
            return False
        return True

    def membro_id_da_interacao(self, interaction: discord.Interaction) -> int | None:
        """Descobre de qual whitelist é o clique: primeiro pela mensagem (as
        mensagens de revisão ficam guardadas), depois pelo canal."""
        msg = getattr(interaction, "message", None)
        if msg is not None:
            for uid, registro in self.dados.items():
                if any(m.get("msg_id") == msg.id for m in registro.get("revisao_msgs", [])):
                    return int(uid)
        if interaction.channel is not None:
            return self._membro_id_do_canal(interaction.channel.id)
        return None

    async def _garantir_acesso_staff(self, canal: discord.TextChannel) -> None:
        """Canais criados antes do cargo da whitelist existir não têm permissão
        pra ele — garante que a staff da whitelist enxerga e fala no canal."""
        cargo = canal.guild.get_role(CARGO_STAFF_WHITELIST_ID)
        if cargo is None:
            return
        atual = canal.overwrites_for(cargo)
        if atual.view_channel and atual.send_messages and atual.read_message_history:
            return
        try:
            await canal.set_permissions(
                cargo, view_channel=True, send_messages=True, read_message_history=True,
                reason="Cargo da whitelist precisa acessar o canal",
            )
        except discord.HTTPException:
            pass

    async def chamar_staff(self, interaction: discord.Interaction):
        """Botão 🔔 do candidato: marca o cargo da whitelist no canal."""
        if not await self.checar_dono(interaction, exigir_andamento=False):
            return
        registro = self.dados.get(str(interaction.user.id), {})
        if registro.get("status") in ("aprovada", "recusada", "cancelada"):
            await interaction.response.send_message("⚠️ Essa whitelist já foi encerrada.", ephemeral=True)
            return

        agora = time.time()
        restante = CHAMAR_STAFF_COOLDOWN_SEGUNDOS - (agora - registro.get("chamou_staff_ts", 0))
        if restante > 0:
            await interaction.response.send_message(
                f"⏳ A staff já foi chamada há pouco. Aguarda mais {int(restante // 60) + 1} min pra chamar de novo.",
                ephemeral=True,
            )
            return

        cargo = interaction.guild.get_role(CARGO_STAFF_WHITELIST_ID)
        if cargo is None:
            await interaction.response.send_message("⚠️ Não achei o cargo da staff de whitelist.", ephemeral=True)
            return

        registro["chamou_staff_ts"] = agora
        salvar("whitelist", self.dados)
        await interaction.response.defer()
        try:
            await self._garantir_acesso_staff(interaction.channel)
        except discord.HTTPException:
            pass
        await _responder(
            interaction,
            f"🔔 {cargo.mention} — {interaction.user.mention} está pedindo ajuda com a whitelist!",
            allowed_mentions=discord.AllowedMentions(roles=[cargo], users=[interaction.user]),
        )


    async def get_categoria(self, guild: discord.Guild) -> discord.CategoryChannel:
        if CATEGORIA_WHITELIST_ID:
            cat = guild.get_channel(CATEGORIA_WHITELIST_ID)
            if isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name=NOME_CATEGORIA_WHITELIST)
        if cat is None:
            cat = await guild.create_category(NOME_CATEGORIA_WHITELIST, reason="Categoria de whitelist criada automaticamente")
        return cat


    async def get_canal_status(self, guild: discord.Guild) -> discord.TextChannel:
        if STATUS_WHITELIST_CHANNEL_ID:
            canal = guild.get_channel(STATUS_WHITELIST_CHANNEL_ID)
            if isinstance(canal, discord.TextChannel):
                return canal
        canal = discord.utils.get(guild.text_channels, name=NOME_CANAL_STATUS)
        if canal is None:
            categoria = await self.get_categoria(guild)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            canal = await guild.create_text_channel(
                name=NOME_CANAL_STATUS,
                category=categoria,
                overwrites=overwrites,
                reason="Canal de status de whitelist criado automaticamente",
            )
        return canal


    async def atualizar_status_board(self, guild: discord.Guild, membro_id: int):
        registro = self.dados.get(str(membro_id))
        if not registro:
            return
        canal_status = await self.get_canal_status(guild)
        status = registro.get("status", "pendente")
        label, cor = STATUS_LABELS.get(status, ("⏳ Pendente", 0xFEE75C))
        membro = guild.get_member(membro_id)
        nome = membro.mention if membro else f"<@{membro_id}>"

        embed = discord.Embed(description=f"{nome} — **{label}**", color=cor)
        if membro:
            embed.set_thumbnail(url=membro.display_avatar.url)

        if status in ("aprovada", "recusada"):
            decidido_por_id = registro.get("decidido_por_id")
            decidido_por_nome = registro.get("decidido_por_nome")
            if decidido_por_id:
                verbo = "Aprovado" if status == "aprovada" else "Recusado"
                embed.add_field(name="Responsável", value=f"{verbo} por <@{decidido_por_id}>", inline=False)
            elif decidido_por_nome:
                verbo = "Aprovado" if status == "aprovada" else "Recusado"
                embed.add_field(name="Responsável", value=f"{verbo} por **{decidido_por_nome}**", inline=False)


        r = registro.get("respostas", {})
        if r:
            embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
            embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
            embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
            embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
            embed.add_field(name="Maior rank", value=f"{r.get('peak_rank', '—')} ({r.get('peak_div', '—')})", inline=True)
            embed.add_field(name="Conta do maior rank", value=r.get("peak_conta", "—"), inline=True)
            embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
            embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
            embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
            embed.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
            embed.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)
            # pergunta nova entra aqui tb, mais um add_field igual esses de cima
            # (tem mais uns 2 lugares no arquivo que montam esse mesmo resumo,
            # procura por "TikTok" que acha todos)

        msg_id = registro.get("status_msg_id")
        if msg_id:
            try:
                msg = await canal_status.fetch_message(msg_id)
                await msg.edit(embed=embed)
                salvar("whitelist", self.dados)
                return
            except discord.NotFound:
                pass

        nova = await canal_status.send(embed=embed)
        registro["status_msg_id"] = nova.id
        salvar("whitelist", self.dados)


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        try:
            await self.criar_canal_whitelist(member)
        except Exception as e:  # sem isso a pessoa entrava e ficava sem canal, sem nenhum aviso
            _log_erro(f"criar_canal_whitelist({member})", e)

    async def criar_canal_whitelist(self, member: discord.Member) -> discord.TextChannel:
        guild = member.guild

        cargo_sem_acesso = guild.get_role(CARGO_SEM_ACESSO_ID)
        if cargo_sem_acesso and cargo_sem_acesso not in member.roles:
            try:
                await member.add_roles(cargo_sem_acesso, reason="Entrou no servidor — aguardando whitelist")
            except discord.Forbidden:
                pass

        # Já tem uma whitelist em aberto? Reaproveita o canal dela.
        registro_atual = self.dados.get(str(member.id))
        if registro_atual and registro_atual.get("status") in ("em_andamento", "pendente", "visualizada"):
            canal_atual = guild.get_channel(registro_atual.get("canal_id") or 0)
            if canal_atual is not None:
                return canal_atual

        # Nome do canal: se já existir um com esse nome (de OUTRA pessoa com
        # nome parecido, ou um canal antigo ainda esperando ser apagado), usa
        # os 4 últimos dígitos do ID pra não misturar as duas whitelists.
        nome_canal = f"whitelist-{_slug(member.name)}"
        if discord.utils.get(guild.text_channels, name=nome_canal):
            nome_canal = f"{nome_canal}-{str(member.id)[-4:]}"

        categoria = await self.get_categoria(guild)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in CARGOS_QUE_VEEM_WHITELIST:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            reason=f"Whitelist de {member}",
        )

        self.dados[str(member.id)] = {"respostas": {}, "status": "em_andamento", "canal_id": canal.id, "criado_ts": time.time()}
        salvar("whitelist", self.dados)

        embed = discord.Embed(
            title="🚀 Bem-vindo(a)! Vamos fazer sua Whitelist",
            description=(
                f"Olá, {member.mention}! Antes de liberar o servidor pra você, "
                f"precisamos te fazer algumas perguntinhas rápidas.\n\n"
                f"Clica no botão abaixo pra começar 👇"
            ),
            color=0x57F287,
        )
        embed.set_footer(text="Leva menos de 2 minutos!")

        await canal.send(content=member.mention, embed=embed, view=ComecarWhitelistView())
        return canal


    async def _audit_recente(self, guild: discord.Guild, acao: discord.AuditLogAction, alvo_id: int):
        """Quem fez a ação (kick/ban) contra `alvo_id` nos últimos segundos."""
        for tentativa in range(2):
            try:
                async for entry in guild.audit_logs(limit=8, action=acao):
                    if (datetime.now(timezone.utc) - entry.created_at).total_seconds() > 20:
                        break
                    if getattr(entry.target, "id", None) == alvo_id:
                        return entry.user, entry.reason
            except (discord.Forbidden, discord.HTTPException):
                return None, None
            if tentativa == 0:
                await asyncio.sleep(1.5)  # o audit log às vezes atrasa um pouco
        return None, None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Guarda banimentos no histórico (usado no aviso antes de aceitar de volta)."""
        executor, motivo = await self._audit_recente(guild, discord.AuditLogAction.ban, user.id)
        registrar_punicao_historico(user.id, "ban", motivo, executor.id if executor else None)

    async def _registrar_se_foi_expulso(self, member: discord.Member) -> None:
        executor, motivo = await self._audit_recente(member.guild, discord.AuditLogAction.kick, member.id)
        if executor is not None or motivo:
            registrar_punicao_historico(member.id, "kick", motivo, executor.id if executor else None)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        asyncio.create_task(self._registrar_se_foi_expulso(member))

        registro = self.dados.get(str(member.id))


        if not registro or registro.get("status") in ("aprovada", "recusada", "cancelada"):
            return
        canal_id = registro.get("canal_id")
        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal:
            try:
                await canal.delete(reason="Membro saiu antes de terminar a whitelist")
            except discord.HTTPException:
                pass
        registro["status"] = "cancelada"
        registro["cancelado_motivo"] = "saiu_do_servidor"
        registro["cancelado_em"] = time.time()
        salvar("whitelist", self.dados)
        try:  # o quadro de status ficava mostrando "Pendente" pra quem já tinha saído
            await self.atualizar_status_board(member.guild, member.id)
        except discord.HTTPException:
            pass


    async def dar_cargo_rank(self, guild: discord.Guild, membro: discord.Member, rank_nome: str) -> str | None:
        """Dá o cargo de divisão (ex.: Champion 2) E o cargo geral do rank
        (Champion). Troca os cargos de rank antigos. Aceita o rank sem divisão
        ("Platina") dando só o cargo geral e avisando a staff."""
        nome = " ".join(str(rank_nome).split())
        cargo_id = CARGO_RANKS.get(nome) or next((i for n, i in CARGO_RANKS.items() if n.lower() == nome.lower()), 0)
        try:
            if cargo_id:
                cargo = guild.get_role(cargo_id)
                if cargo is None:
                    return f"⚠️ Não achei o cargo do rank **{nome}** no servidor (confira o ID em cogs/players.py)."
                await aplicar_cargo_rank(membro, cargo, "Whitelist — rank aplicado")
                return None

            geral_id = next((i for t, i in CARGO_GERAL_SEM_DIVISAO_IDS.items() if t.lower() == nome.lower()), 0)
            geral = guild.get_role(geral_id) if geral_id else None
            if geral is None:
                return f"⚠️ Não achei o cargo do rank **{nome}**."
            # rank sem divisão: dá só o cargo geral (e tira os de rank antigos)
            ids_rank = set(CARGO_RANKS.values()) | set(CARGO_GERAL_SEM_DIVISAO_IDS.values())
            remover = [r for r in membro.roles if r.id in ids_rank and r.id != geral.id]
            if remover:
                await membro.remove_roles(*remover, reason="Whitelist — rank aplicado")
            if geral not in membro.roles:
                await membro.add_roles(geral, reason="Whitelist — rank aplicado")
            return f"⚠️ O rank **{nome}** veio sem divisão: dei só o cargo **{geral.name}**. Ajuste a divisão depois."
        except discord.Forbidden:
            return "⚠️ Não tenho permissão pra dar o cargo de rank."
        except discord.HTTPException as e:
            return f"⚠️ Erro do Discord ao dar o cargo de rank: {e}"

    async def dar_cargo_plataforma(self, guild: discord.Guild, membro: discord.Member, plataforma: str) -> str | None:
        """Dá o cargo da plataforma (PC / Xbox / PlayStation) e tira os outros
        cargos de plataforma. Switch não tem cargo."""
        cargo_id = CARGOS_PLATAFORMA_IDS.get(plataforma)
        if cargo_id is None:
            return None
        cargo = guild.get_role(cargo_id)
        if cargo is None:
            return f"⚠️ Não achei o cargo da plataforma **{plataforma}**."
        outros = [r for r in membro.roles if r.id in CARGOS_PLATAFORMA_IDS.values() and r.id != cargo.id]
        try:
            if outros:
                await membro.remove_roles(*outros, reason="Whitelist — troca de plataforma")
            if cargo not in membro.roles:
                await membro.add_roles(cargo, reason="Whitelist — plataforma aplicada")
        except discord.Forbidden:
            return "⚠️ Não tenho permissão pra dar o cargo de plataforma."
        return None


    async def prosseguir_apos_habilidades(self, canal: discord.TextChannel, membro: discord.Member):
        registro = self.dados.get(str(membro.id), {})
        tem_tiktok = registro.get("respostas", {}).get("tem_tiktok")
        if tem_tiktok == "Sim":
            await self.enviar_pergunta(canal, membro, "perguntas_abertas")
        else:
            await self.enviar_pergunta(canal, membro, "duvidas")


    # ── controle de etapa: retomar pergunta, travas e recuperação ──────────
    ORDEM_ETAPAS = ["idioma", "rank", "rank_divisao", "plataforma", "peak_rank", "peak_div", "peak_conta",
                    "tempo", "microfone", "ativo", "tem_tiktok", "habilidades", "perguntas_abertas", "duvidas"]

    def trava(self, membro_id: int) -> asyncio.Lock:
        """Um lock por pessoa: clique duplo / dois cliques ao mesmo tempo não duplicam etapas."""
        return self._locks.setdefault(membro_id, asyncio.Lock())

    def etapa_valida(self, membro_id: int, step: str) -> bool:
        """O clique é na pergunta ATUAL? (menu antigo/duplicado não pode mais mexer no fluxo)
        Whitelists de antes dessa função não têm etapa guardada: aceitam tudo, como antes."""
        etapa = self.dados.get(str(membro_id), {}).get("etapa_atual")
        return etapa is None or etapa == step

    @staticmethod
    def _inferir_etapa(respostas: dict) -> str:
        """Etapa em que a pessoa está, pelas respostas já dadas (usado quando não há etapa guardada)."""
        if not respostas.get("idioma"):
            return "idioma"
        rank = respostas.get("rank")
        if not rank:
            return "rank"
        if rank in RANK_TIERS_COM_DIVISAO:       # escolheu o tier mas não a divisão
            return "rank_divisao"
        for chave in ("plataforma", "peak_rank"):
            if not respostas.get(chave):
                return chave
        for chave in ("peak_div", "peak_conta", "tempo", "microfone", "ativo", "tem_tiktok"):
            if not respostas.get(chave):
                return chave
        if not respostas.get("habilidades"):
            return "habilidades"
        if respostas.get("tem_tiktok") == "Sim" and not respostas.get("tiktok"):
            return "perguntas_abertas"
        return "duvidas"

    async def enviar_pergunta(self, canal: discord.TextChannel, membro: discord.Member, step: str) -> bool:
        """Manda a pergunta da etapa e guarda onde a pessoa está. NUNCA estoura: se o envio
        falhar, a etapa fica marcada como 'não enviada' e o bot reenvia sozinho em ~1 min."""
        registro = self.dados.get(str(membro.id))
        if registro is not None:
            registro["etapa_atual"] = step
            registro["etapa_enviada"] = False
            registro["etapa_ts"] = time.time()
            salvar("whitelist", self.dados)
        try:
            msg = await self._montar_e_enviar_pergunta(canal, membro, step)
        except Exception as e:
            _log_erro(f"enviar_pergunta({step})", e)
            return False
        if registro is not None:
            registro["etapa_enviada"] = True
            registro["etapa_msg_id"] = getattr(msg, "id", None)
            registro["etapa_tentativas"] = 0
            salvar("whitelist", self.dados)
        return True

    async def processar_escolha(self, interaction: discord.Interaction, step: str, valor: str, prox_step: str | None):
        """Grava a resposta de um menu, confirma pra pessoa e manda a próxima pergunta."""
        membro = interaction.user
        canal = interaction.channel
        try:
            self.salvar_resposta(membro.id, step, valor)
            texto = f"✅ Resposta registrada: **{valor}**"
            proximo = prox_step

            if step == "idioma":
                guild = interaction.guild
                cargo_ingles = guild.get_role(CARGO_IDIOMA_INGLES_ID)
                falantes_ingles = sum(
                    1 for m in (cargo_ingles.members if cargo_ingles else [])
                    if not m.bot and m.id != membro.id
                )
                total_humanos = sum(1 for m in guild.members if not m.bot and m.id != membro.id)
                contagem = falantes_ingles if valor == "Inglês" else max(0, total_humanos - falantes_ingles)

                cargo_msg = ""
                if valor == "Inglês":
                    if cargo_ingles:
                        try:
                            await membro.add_roles(cargo_ingles, reason="Whitelist — idioma Inglês selecionado")
                            cargo_msg = f"\n🏷️ Cargo {cargo_ingles.mention} atribuído!"
                        except discord.HTTPException:
                            cargo_msg = "\n⚠️ Não consegui atribuir o cargo de idioma (permissão)."
                    else:
                        cargo_msg = "\n⚠️ Cargo de idioma configurado não foi encontrado no servidor."
                texto = (
                    f"✅ Idioma registrado: **{valor}**.\n"
                    f"🌐 Mais **{contagem}** pessoa(s) falam o mesmo idioma que você.{cargo_msg}"
                )
            elif step == "rank":
                if valor in RANK_TIERS_COM_DIVISAO:
                    texto = f"✅ Rank registrado: **{valor}**. Agora escolhe a divisão! 🔢"
                    proximo = "rank_divisao"
                else:
                    # Super Sonic Legend não tem divisão, já vai direto pra próxima etapa
                    texto = f"✅ Rank registrado: **{valor}**.\n*(o cargo só é aplicado se a whitelist for aprovada)*"
                    proximo = "plataforma"
            elif step == "rank_divisao":
                tier = self.dados.get(str(membro.id), {}).get("respostas", {}).get("rank", "")
                rank_completo = f"{tier} {valor}".strip()
                self.salvar_resposta(membro.id, "rank", rank_completo)
                texto = f"✅ Divisão registrada: **{rank_completo}**.\n*(o cargo só é aplicado se a whitelist for aprovada)*"
                proximo = "plataforma"
            elif step == "peak_rank" and valor == "Supersonic Legend":
                self.salvar_resposta(membro.id, "peak_div", "—")
                proximo = "peak_conta"
            elif step == "tem_tiktok" and valor == "Não":
                self.salvar_resposta(membro.id, "tiktok", "Não possui")
                proximo = "habilidades"

            await _responder(interaction, texto)
            if proximo:
                await self.enviar_pergunta(canal, membro, proximo)
        except Exception as e:
            # a resposta pode ter sido gravada, mas o fluxo não andou: deixa a etapa marcada como
            # 'não enviada' (o bot reenvia a pergunta sozinho) e avisa a pessoa
            _log_erro(f"processar_escolha({step})", e)
            registro = self.dados.get(str(membro.id))
            if registro is not None:
                registro["etapa_enviada"] = False
                registro["etapa_ts"] = time.time()
                salvar("whitelist", self.dados)
            await _responder(interaction, MSG_ERRO_ETAPA + " (vou reenviar a pergunta sozinho em instantes)")

    async def reenviar_etapa(self, canal: discord.TextChannel, membro: discord.Member) -> str:
        """Refaz a pergunta em que a pessoa parou (apaga a antiga, se ainda existir).
        Devolve o texto pra mostrar pra ela."""
        registro = self.dados.get(str(membro.id))
        if not registro or registro.get("status") != "em_andamento":
            return "⚠️ Sua whitelist já foi enviada pra análise — não tem mais pergunta pra refazer."
        respostas = registro.get("respostas", {})
        if not respostas.get("nick"):
            return "👉 Você ainda não começou: clique em **🚀 Começar Whitelist** na primeira mensagem do canal."

        step = registro.get("etapa_atual") or self._inferir_etapa(respostas)
        antiga = registro.get("etapa_msg_id")
        if antiga:
            try:
                msg = await canal.fetch_message(antiga)
                await msg.delete()
            except discord.HTTPException:
                pass
        ok = await self.enviar_pergunta(canal, membro, step)
        if not ok:
            return "⚠️ Não consegui reenviar agora. Tento de novo sozinho em instantes — se não aparecer, clique em **🔄 Refazer pergunta**."
        return "🔄 Pronto! Reenviei a pergunta em que você parou — é só responder lá embaixo. 👇"

    @tasks.loop(minutes=1)
    async def retomar_etapas_whitelist(self):
        """Se a pergunta de alguém não chegou a ser enviada (erro do Discord, bot reiniciou no
        meio...), reenvia sozinho. No máximo 5 tentativas por etapa, 1 por minuto."""
        agora = time.time()
        for uid_str, registro in list(self.dados.items()):
            if registro.get("status") != "em_andamento" or registro.get("canal_apagado"):
                continue
            if not registro.get("etapa_atual") or registro.get("etapa_enviada", True):
                continue
            if agora - registro.get("etapa_ts", 0) < 60 or registro.get("etapa_tentativas", 0) >= 5:
                continue
            canal = self.bot.get_channel(registro.get("canal_id") or 0)
            membro = canal.guild.get_member(int(uid_str)) if canal else None
            if canal is None or membro is None:
                continue
            registro["etapa_tentativas"] = registro.get("etapa_tentativas", 0) + 1
            await self.reenviar_etapa(canal, membro)

    @retomar_etapas_whitelist.before_loop
    async def antes_retomar_etapas(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="retomar_whitelist", description="Travou na whitelist? Reenvia a pergunta em que você parou.")
    async def retomar_whitelist(self, interaction: discord.Interaction):
        membro_id = self._membro_id_do_canal(interaction.channel.id) if interaction.channel else None
        if membro_id is None or membro_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Use esse comando dentro do canal da sua whitelist.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        texto = await self.reenviar_etapa(interaction.channel, interaction.user)
        await interaction.followup.send(texto, ephemeral=True)

    @staticmethod
    def _config_escolha() -> dict:
        """Etapas de múltipla escolha: (opções, placeholder, próxima etapa, emojis)."""
        return {
            "idioma":       (IDIOMAS, "Escolha seu idioma...", "rank", IDIOMA_EMOJIS),
            "rank":         (RANK_TIERS_ORDEM, "Escolha seu rank atual...", "rank_divisao", RANK_TIER_EMOJIS),
            "rank_divisao": (RANK_DIVISOES_OPCOES, "Escolha a divisão...", "plataforma", None),
            "plataforma":   (PLATAFORMAS, "Escolha sua plataforma...", "peak_rank", None),
            "peak_rank":    (PEAK_RANKS, "Escolha o maior rank já alcançado...", "peak_div", None),
            "peak_div":     (DIVISOES, "Escolha a divisão...", "peak_conta", None),
            "peak_conta":   (PEAK_CONTAS, "Foi nesta conta ou em outra?", "tempo", None),
            "tempo":        (TEMPOS_JOGANDO, "Escolha há quanto tempo joga...", "microfone", None),
            "microfone":    (["Sim", "Não"], "Você tem microfone?", "ativo", None),
            "ativo":        (["Sim", "Não"], "Você vai ser ativo?", "tem_tiktok", None),
            "tem_tiktok":   (["Sim", "Não"], "Você tem TikTok?", "habilidades", None),
        }

    def _view_escolha(self, step: str) -> "EscolhaView":
        opcoes, placeholder, prox, emojis = self._config_escolha()[step]
        return EscolhaView(self, step, opcoes, placeholder, prox, emojis=emojis)

    async def _montar_e_enviar_pergunta(self, canal: discord.TextChannel, membro: discord.Member, step: str):
        msg = None
        if step == "idioma":
            view = self._view_escolha("idioma")
            msg = await canal.send("🌐 **Qual é a sua linguagem?**\n(Português ou Inglês — só pode escolher uma)", view=view)

        elif step == "rank":
            view = self._view_escolha("rank")
            msg = await canal.send("🎮 **Qual o seu rank atual no Rocket League?**", view=view)

        elif step == "rank_divisao":
            registro = self.dados.get(str(membro.id), {})
            tier = registro.get("respostas", {}).get("rank", "")
            view = self._view_escolha("rank_divisao")
            msg = await canal.send(f"🔢 **Qual divisão do seu rank {tier}?** (1, 2 ou 3)", view=view)

        elif step == "plataforma":
            view = self._view_escolha("plataforma")
            msg = await canal.send("🖥️ **Em qual plataforma você joga?**", view=view)

        elif step == "peak_rank":
            view = self._view_escolha("peak_rank")
            msg = await canal.send("🏆 **Qual o maior rank que você já alcançou?**", view=view)

        elif step == "peak_div":
            view = self._view_escolha("peak_div")
            msg = await canal.send("🔢 **E qual divisão desse rank?**", view=view)

        elif step == "peak_conta":
            view = self._view_escolha("peak_conta")
            msg = await canal.send("🔁 **Esse maior rank foi alcançado na conta que você joga hoje ou em outra conta?**", view=view)

        elif step == "tempo":
            view = self._view_escolha("tempo")
            msg = await canal.send("⏱️ **Há quanto tempo você joga Rocket League?**", view=view)

        elif step == "microfone":
            view = self._view_escolha("microfone")
            msg = await canal.send("🎤 **Você tem microfone pra jogar?**", view=view)

        elif step == "ativo":
            view = self._view_escolha("ativo")
            msg = await canal.send("📈 **Você pretende ser um membro ativo na equipe?**", view=view)

        elif step == "tem_tiktok":
            view = self._view_escolha("tem_tiktok")
            msg = await canal.send("🎵 **Você tem conta no TikTok?**", view=view)

        elif step == "habilidades":
            embed = discord.Embed(
                title="🛠️ Alguma habilidade extra?",
                description=(
                    "Você tem alguma dessas habilidades? **(opcional, pode selecionar mais de uma ou pular)**\n\n"
                    + "\n".join(f"• {h}" for h in HABILIDADES)
                ),
                color=0x5865F2,
            )
            msg = await canal.send(embed=embed, view=HabilidadesView())

        elif step == "perguntas_abertas":
            embed = discord.Embed(
                title="📝 Última pergunta",
                description=(
                    "Só falta mais uma coisa. Clica no botão abaixo pra abrir o formulário:\n\n"
                    "• Qual o seu usuário do TikTok? (só o @ já serve)"
                    # se add pergunta nova no modal, bota ela aqui também
                    # nessa listinha, só copia o padrão de cima
                ),
                color=0x5865F2,
            )
            msg = await canal.send(embed=embed, view=AbrirPerguntasView(self))

        elif step == "duvidas":
            embed = discord.Embed(
                title="❓ Alguma dúvida?",
                description=(
                    "Antes de finalizar, fica à vontade pra mandar aqui **qualquer dúvida** que "
                    "você tenha sobre o servidor, a equipe ou como tudo funciona — pode mandar "
                    "quantas quiser, a staff vai te responder por aqui mesmo.\n\n"
                    "Quando não tiver mais nenhuma, clica em **Concluir Whitelist** abaixo. ✅"
                ),
                color=0x5865F2,
            )
            msg = await canal.send(embed=embed, view=FinalizarWhitelistView())
        return msg


    async def solicitar_aprovacao(self, interaction: discord.Interaction):
        # só o dono, e só uma vez (antes dava pra clicar 2x e duplicar a revisão)
        if not await self.checar_dono(interaction):
            return
        membro = interaction.user
        guild = interaction.guild
        registro = self.dados[str(membro.id)]

        registro["status"] = "pendente"
        registro["enviado_ts"] = time.time()
        salvar("whitelist", self.dados)

        await interaction.response.send_message(
            "📨 **Suas respostas foram enviadas!** Um administrador vai revisar e te avisar por aqui assim que decidir. Aguenta aí! ⏳"
        )

        try:
            await interaction.channel.set_permissions(membro, send_messages=False, view_channel=True)
        except discord.Forbidden:
            pass
        await self._garantir_acesso_staff(interaction.channel)

        await self.atualizar_status_board(guild, membro.id)

        r = registro["respostas"]

        embed_resumo = discord.Embed(
            title=f"📋 Resumo da Whitelist — {membro}",
            description="Confira as respostas antes de decidir abaixo.",
            color=0x5865F2,
        )
        embed_resumo.set_thumbnail(url=membro.display_avatar.url)
        self._campos_resumo(embed_resumo, registro)
        embed_resumo.set_footer(text=f"ID: {membro.id}")
        msg_resumo = await interaction.channel.send(embed=embed_resumo)

        embed_revisao = discord.Embed(
            title="🔎 Whitelist aguardando revisão",
            description=f"Analisa as respostas de {membro.mention} e decide abaixo.\n(apenas a **staff da whitelist**)",
            color=0xFEE75C,
        )
        msg_revisao = await interaction.channel.send(embed=embed_revisao, view=RevisaoWhitelistView(tracker_url=url_tracker(r)))
        # guarda as mensagens de revisão: é por elas que o clique descobre de quem é a whitelist
        revisao_msgs = [{"canal_id": interaction.channel.id, "msg_id": msg_revisao.id}]

        if CANAL_LOG_WHITELIST_ID:
            canal_log = self.bot.get_channel(CANAL_LOG_WHITELIST_ID)
            if canal_log:
                embed = discord.Embed(
                    title=f"📋 Whitelist enviada para análise — {membro}",
                    description=f"{membro.mention} terminou a whitelist. Revise aqui ou abra o chat. 👇",
                    color=0xFEE75C,
                )
                embed.set_thumbnail(url=membro.display_avatar.url)
                self._campos_resumo(embed, registro)
                embed.set_footer(text=f"ID: {membro.id}")
                try:
                    # mesmos botões de revisão + 📂 "Abrir chat da whitelist" ao lado
                    msg_log = await canal_log.send(embed=embed, view=RevisaoWhitelistView(guild.id, interaction.channel.id, url_tracker(r)))
                    revisao_msgs.append({"canal_id": canal_log.id, "msg_id": msg_log.id})
                except discord.HTTPException as e:
                    print(f"[WHITELIST] ⚠️ Não consegui enviar a revisão pro canal de log: {e}")

        registro["revisao_msgs"] = revisao_msgs
        # guarda o resumo do canal pra conseguir atualizar quando a staff editar uma resposta
        registro["resumo_msg"] = {"canal_id": interaction.channel.id, "msg_id": msg_resumo.id}
        salvar("whitelist", self.dados)

    async def marcar_visualizada(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        membro_id = self.membro_id_da_interacao(interaction)
        registro = self.dados.get(str(membro_id)) if membro_id else None
        if not registro:
            await interaction.followup.send("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return

        # antes dava pra "visualizar" uma whitelist JÁ decidida (o status voltava
        # pra "em análise") e outro admin podia roubar a análise de quem já tinha pego
        status = registro.get("status")
        if status in ("aprovada", "recusada", "cancelada"):
            await interaction.followup.send(f"⚠️ Essa whitelist já está **{status}**.", ephemeral=True)
            return
        dono_analise = registro.get("visualizado_por_id")
        if dono_analise is not None and dono_analise != interaction.user.id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            await interaction.followup.send(f"⚠️ Essa whitelist já está em análise por **{nome}**.", ephemeral=True)
            return

        registro["status"] = "visualizada"
        registro["visualizado_por_id"] = interaction.user.id
        registro["visualizado_por_nome"] = str(interaction.user)
        salvar("whitelist", self.dados)
        await self.atualizar_status_board(interaction.guild, membro_id)

        canal = self.bot.get_channel(registro.get("canal_id") or 0)
        if canal is not None:
            try:
                await canal.send(
                    f"👀 Marcada como em análise por {interaction.user.mention}. "
                    f"A partir de agora, só {interaction.user.mention} pode aprovar ou recusar essa whitelist."
                )
            except discord.HTTPException:
                pass
        await interaction.followup.send("👀 Pronto, a whitelist está marcada como em análise por você.", ephemeral=True)

    # ── chat do candidato + edição das respostas (staff) ───────────────────
    @staticmethod
    def _campos_resumo(embed: discord.Embed, registro: dict) -> None:
        """Campos do resumo da whitelist — usado no resumo do canal, na mensagem
        do canal de log e no menu de edição. Pergunta nova: add_field aqui
        (e no status board, mais abaixo, que monta o seu próprio)."""
        r = registro.get("respostas", {})
        embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
        embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
        embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
        embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
        embed.add_field(name="Maior rank", value=f"{r.get('peak_rank', '—')} ({r.get('peak_div', '—')})", inline=True)
        embed.add_field(name="Conta do maior rank", value=r.get("peak_conta", "—"), inline=True)
        embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
        embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
        embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
        embed.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
        embed.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)

        edicoes = registro.get("edicoes") or []
        if edicoes:
            linhas = [
                f"• **{_limpo(e.get('rotulo', '?'))}**: {_limpo(e.get('de', '—'))} → {_limpo(e.get('para', '—'))} "
                f"(por {_limpo(e.get('por_nome', '?'))})"
                for e in edicoes[-5:]
            ]
            if len(edicoes) > 5:
                linhas.insert(0, f"*(+{len(edicoes) - 5} edição(ões) anterior(es))*")
            embed.add_field(name="✏️ Editado pela staff", value="\n".join(linhas)[:1024], inline=False)

    @staticmethod
    def _bloqueio_analise(registro: dict | None, autor_id: int) -> str | None:
        """Trava geral de "em análise": depois que um manager clicou em
        👀 Marcar como Visualizada, SÓ ele mexe na whitelist (abrir/fechar chat,
        editar, aprovar, recusar). Vale pra qualquer outro staff, admin e
        até o dono do bot. Devolve o aviso, ou None se pode seguir."""
        if not registro:
            return None
        dono = registro.get("visualizado_por_id")
        if dono is not None and dono != autor_id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            return f"🔒 Essa whitelist está em análise por **{_limpo(nome)}** — só ela(e) pode mexer nela."
        return None

    def _bloqueio_edicao(self, membro_id: int, autor_id: int) -> str | None:
        """Quando a staff NÃO pode editar. Devolve o aviso, ou None se pode."""
        registro = self.dados.get(str(membro_id))
        if not registro:
            return "⚠️ Não achei os dados dessa whitelist."
        status = registro.get("status")
        if status in ("aprovada", "recusada", "cancelada"):
            return f"⚠️ Essa whitelist já está **{status}** — pra corrigir depois disso use o comando `/editar_whitelist`."
        if status == "em_andamento":
            return "⚠️ O candidato ainda está respondendo — espera ele enviar a whitelist pra editar."
        visualizado_por_id = registro.get("visualizado_por_id")
        if visualizado_por_id is not None and visualizado_por_id != autor_id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            return f"⚠️ Essa whitelist está em análise por **{_limpo(nome)}** — só ela(e) pode editar."
        return None

    def _embed_edicao(self, guild: discord.Guild, membro_id: int) -> discord.Embed:
        registro = self.dados.get(str(membro_id), {})
        membro = guild.get_member(membro_id) if guild else None
        embed = discord.Embed(
            title=f"✏️ Editar whitelist — {membro or membro_id}",
            description="Escolha no menu qual resposta quer corrigir.\n"
                        "*(rank e plataforma só viram cargo quando a whitelist for aprovada)*",
            color=0xFEE75C,
        )
        if membro:
            embed.set_thumbnail(url=membro.display_avatar.url)
        self._campos_resumo(embed, registro)
        return embed

    async def abrir_edicao(self, interaction: discord.Interaction):
        """Clique em ✏️ Editar respostas."""
        membro_id = self.membro_id_da_interacao(interaction)
        if membro_id is None:
            await interaction.response.send_message("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return
        bloqueio = self._bloqueio_edicao(membro_id, interaction.user.id)
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return
        await interaction.response.send_message(
            embed=self._embed_edicao(interaction.guild, membro_id),
            view=EditarCampoView(self, membro_id, interaction.user.id),
            ephemeral=True,
        )

    async def aplicar_edicao(self, guild: discord.Guild, autor: discord.abc.User, membro_id: int, chave: str, valor: str) -> tuple[bool, str]:
        """Grava a correção da staff. Devolve (mudou, texto pra mostrar pra staff)."""
        if not _pode_gerir(autor):
            return False, "❌ Só a staff da whitelist pode editar."
        bloqueio = self._bloqueio_edicao(membro_id, autor.id)
        if bloqueio:
            return False, bloqueio
        if chave not in CAMPOS_EDITAVEIS:
            return False, "⚠️ Campo inválido."

        if chave == "tiktok":
            valor, erro = normalizar_tiktok(valor)
            if erro:
                return False, f"⚠️ {erro}"

        rotulo = CAMPOS_EDITAVEIS[chave][0]
        registro = self.dados[str(membro_id)]
        respostas = registro.setdefault("respostas", {})
        antigo = respostas.get(chave, "—")
        if antigo == valor:
            return False, f"ℹ️ **{rotulo}** já está como **{_limpo(valor)}** — nada mudou."

        respostas[chave] = valor
        membro = guild.get_member(membro_id)
        notas = []

        if chave == "nick" and membro:
            # o fluxo normal já troca o apelido do candidato quando ele responde; mantém igual
            try:
                await membro.edit(nick=valor, reason=f"Whitelist editada por {autor}")
            except discord.HTTPException:
                notas.append("⚠️ Não consegui atualizar o apelido do membro (permissão/hierarquia).")
        elif chave == "idioma" and membro:
            # o cargo de inglês é dado na hora da resposta, então acompanha a correção
            cargo = guild.get_role(CARGO_IDIOMA_INGLES_ID)
            if cargo:
                try:
                    if valor == "Inglês" and cargo not in membro.roles:
                        await membro.add_roles(cargo, reason=f"Whitelist editada por {autor}")
                    elif valor != "Inglês" and cargo in membro.roles:
                        await membro.remove_roles(cargo, reason=f"Whitelist editada por {autor}")
                except discord.HTTPException:
                    notas.append("⚠️ Não consegui ajustar o cargo de idioma.")
        elif chave == "peak_rank":
            if valor == "Supersonic Legend":
                respostas["peak_div"] = "—"
            elif respostas.get("peak_div") in (None, "—"):
                notas.append("⚠️ Falta escolher também a **divisão do maior rank**.")
        elif chave == "tem_tiktok":
            if valor == "Não":
                respostas["tiktok"] = "Não possui"
                notas.append("ℹ️ TikTok marcado como \"Não possui\".")
            elif respostas.get("tiktok") in (None, "—", "Não possui"):
                respostas["tiktok"] = "—"
                notas.append("⚠️ Falta editar também o **link do TikTok**.")
        elif chave in ("rank", "plataforma"):
            notas.append("ℹ️ O cargo só é aplicado quando a whitelist for aprovada.")

        registro.setdefault("edicoes", []).append({
            "campo": chave,
            "rotulo": rotulo,
            "de": antigo,
            "para": valor,
            "por_id": autor.id,
            "por_nome": str(autor),
            "ts": time.time(),
        })
        salvar("whitelist", self.dados)

        await self._atualizar_embeds_revisao(registro)
        try:
            await self.atualizar_status_board(guild, membro_id)
        except discord.HTTPException:
            pass

        canal = self.bot.get_channel(registro.get("canal_id") or 0)
        if canal is not None:
            try:
                await canal.send(
                    f"✏️ {autor.mention} corrigiu **{rotulo}**: {_limpo(antigo)} → **{_limpo(valor)}**",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass

        texto = f"✅ **{rotulo}** corrigido: {_limpo(antigo)} → **{_limpo(valor)}**"
        if notas:
            texto += "\n" + "\n".join(notas)
        return True, texto

    async def _atualizar_embeds_revisao(self, registro: dict) -> None:
        """Reescreve os campos do resumo do canal e da mensagem do log (as
        mensagens ficam no lugar, com os mesmos botões)."""
        refs = list(registro.get("revisao_msgs", []))
        if registro.get("resumo_msg"):
            refs.append(registro["resumo_msg"])
        for ref in refs:
            canal = self.bot.get_channel(ref.get("canal_id") or 0)
            if canal is None:
                continue
            try:
                msg = await canal.fetch_message(ref["msg_id"])
                kwargs = {}
                if ref in registro.get("revisao_msgs", []):
                    # nick/plataforma podem ter mudado: refaz o botão do tracker
                    no_log = ref.get("canal_id") != registro.get("canal_id")
                    kwargs["view"] = RevisaoWhitelistView(
                        canal.guild.id if no_log else None,
                        registro.get("canal_id") if no_log else None,
                        url_tracker(registro.get("respostas")),
                    )
                if msg.embeds and any(f.name == "Nick RL" for f in msg.embeds[0].fields):
                    embed = msg.embeds[0].copy()
                    embed.clear_fields()
                    self._campos_resumo(embed, registro)
                    kwargs["embed"] = embed
                if kwargs:  # a mensagem de revisão do canal não tem o resumo: só o botão muda
                    await msg.edit(**kwargs)
            except discord.HTTPException:
                continue

    async def alternar_chat(self, interaction: discord.Interaction):
        """Botão 💬: libera (ou trava de novo) o chat do candidato no canal da
        whitelist. Depois que ele envia as respostas o bot tira a permissão
        dele de falar — esse botão devolve pra staff conseguir conversar."""
        await interaction.response.defer(ephemeral=True)
        membro_id = self.membro_id_da_interacao(interaction)
        registro = self.dados.get(str(membro_id)) if membro_id else None
        if not registro:
            await interaction.followup.send("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return
        status = registro.get("status")
        if status in ("aprovada", "recusada", "cancelada"):
            await interaction.followup.send(f"⚠️ Essa whitelist já está **{status}**.", ephemeral=True)
            return
        if status == "em_andamento":
            await interaction.followup.send("ℹ️ O candidato ainda está respondendo — o chat dele já está liberado.", ephemeral=True)
            return
        bloqueio = self._bloqueio_analise(registro, interaction.user.id)
        if bloqueio:
            await interaction.followup.send(bloqueio, ephemeral=True)
            return

        canal = self.bot.get_channel(registro.get("canal_id") or 0)
        membro = interaction.guild.get_member(membro_id)
        if canal is None or membro is None:
            await interaction.followup.send("⚠️ O canal da whitelist ou o membro não existe mais.", ephemeral=True)
            return

        aberto = canal.overwrites_for(membro).send_messages is True
        try:
            await canal.set_permissions(
                membro, view_channel=True, send_messages=not aberto,
                reason=f"Chat da whitelist {'travado' if aberto else 'liberado'} por {interaction.user}",
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"⚠️ Não consegui mudar a permissão do canal: {e}", ephemeral=True)
            return

        if aberto:
            await canal.send(f"🔒 Chat travado de novo por {interaction.user.mention}.", allowed_mentions=discord.AllowedMentions.none())
            await interaction.followup.send("🔒 Chat travado. Clica de novo pra liberar.", ephemeral=True)
        else:
            await canal.send(
                f"💬 {membro.mention}, a staff liberou o chat: {interaction.user.mention} quer conversar com você. "
                f"Pode responder aqui!",
                allowed_mentions=discord.AllowedMentions(users=[membro, interaction.user]),
            )
            await interaction.followup.send("💬 Chat liberado. Clica de novo pra travar.", ephemeral=True)

    # ── decisão: aprovar / recusar ─────────────────────────────────────────
    def _bloqueio_decisao(self, membro_id: int, autor_id: int) -> str | None:
        """Travas comuns de aprovar/recusar. Devolve o aviso, ou None se pode seguir."""
        registro = self.dados.get(str(membro_id))
        if not registro:
            return "⚠️ Não achei os dados dessa whitelist."
        status = registro.get("status")
        if status in ("aprovada", "recusada"):
            acao = "aprovada" if status == "aprovada" else "recusada"
            quem = registro.get("decidido_por_nome", "outro administrador")
            return f"⚠️ Essa whitelist já foi **{acao}** por **{quem}** — ninguém mais precisa mexer nela."
        if status == "cancelada":
            return "⚠️ Essa whitelist foi cancelada — não dá mais pra aprovar ou recusar."
        visualizado_por_id = registro.get("visualizado_por_id")
        if visualizado_por_id is not None and visualizado_por_id != autor_id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            return f"⚠️ Essa whitelist foi marcada como em análise por **{nome}** — só ela(e) pode aprovar ou recusar."
        return None

    async def _aviso_confirmacao(self, guild: discord.Guild, membro_id: int, aprovar: bool) -> str | None:
        """Texto da confirmação pedida antes da decisão (ou None se não precisa).
        • Aprovar: só pede se a pessoa JÁ FOI expulsa/banida alguma vez.
        • Recusar: sempre pede (recusar expulsa o membro)."""
        membro = guild.get_member(membro_id)
        mencao = membro.mention if membro else f"<@{membro_id}>"
        if not aprovar:
            return (
                f"⚠️ **Tem certeza que quer recusar a whitelist de {mencao}?**\n"
                f"Isso vai **expulsar** a pessoa do servidor automaticamente."
            )
        historico = await buscar_historico(guild, membro_id)
        if not historico:
            return None
        return texto_aviso_historico(mencao, historico)

    async def iniciar_decisao(self, interaction: discord.Interaction, aprovar: bool):
        """Clique em ✅ Aprovar / ❌ Recusar."""
        # defer logo de cara: buscar histórico + mexer em cargos passa fácil dos 3s do Discord
        await interaction.response.defer(ephemeral=True)
        membro_id = self.membro_id_da_interacao(interaction)
        if membro_id is None:
            await interaction.followup.send("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return
        bloqueio = self._bloqueio_decisao(membro_id, interaction.user.id)
        if bloqueio:
            await interaction.followup.send(bloqueio, ephemeral=True)
            return

        aviso = await self._aviso_confirmacao(interaction.guild, membro_id, aprovar)
        if aviso:
            view = ConfirmarDecisaoView(membro_id, interaction.user.id, aprovar)
            view.interaction = interaction
            await interaction.followup.send(
                aviso, view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
            return

        erro, mensagem = await self.decidir(interaction.guild, membro_id, interaction.user, aprovar)
        ok = "✅ Whitelist aprovada!" if aprovar else "✅ Whitelist recusada!"
        await interaction.followup.send(mensagem if erro else ok, ephemeral=True)

    async def fluxo_comando_decisao(self, ctx: commands.Context, aprovar: bool):
        """!aprovar-whitelist / !reprovar-whitelist — mesmas confirmações dos botões."""
        membro_id = self._membro_id_do_canal(ctx.channel.id)
        if membro_id is None:
            await ctx.send("⚠️ Esse comando só funciona dentro do canal de whitelist de um membro.", delete_after=8)
            return
        bloqueio = self._bloqueio_decisao(membro_id, ctx.author.id)
        if bloqueio:
            await ctx.send(bloqueio)
            return
        aviso = await self._aviso_confirmacao(ctx.guild, membro_id, aprovar)
        if aviso:
            view = ConfirmarDecisaoView(membro_id, ctx.author.id, aprovar, forcar_publico=True)
            view.message = await ctx.send(aviso, view=view, allowed_mentions=discord.AllowedMentions.none())
            return
        erro, mensagem = await self.decidir(ctx.guild, membro_id, ctx.author, aprovar)
        if erro:
            await ctx.send(mensagem)

    async def decidir(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, aprovar: bool) -> tuple[bool, str]:
        """Executa a decisão e publica o resultado no CANAL DA WHITELIST (o clique
        pode ter vindo do canal de log). Devolve (erro, mensagem)."""
        registro = self.dados.get(str(membro_id))
        canal = self.bot.get_channel(registro.get("canal_id") or 0) if registro else None
        core = self.aprovar_core if aprovar else self.recusar_core
        erro, mensagem = await core(guild, membro_id, autor, canal)
        if erro:
            return True, mensagem
        if canal is not None:
            try:
                await canal.send(mensagem)
            except discord.HTTPException:
                pass
        await self._fechar_mensagens_revisao(registro, autor, aprovar)
        return False, mensagem

    async def _fechar_mensagens_revisao(self, registro: dict, autor: discord.abc.User, aprovar: bool) -> None:
        """Tira os botões das mensagens de revisão (canal + log) e marca a decisão."""
        cor = 0x57F287 if aprovar else 0xED4245
        texto = f"{'✅ Aprovada' if aprovar else '❌ Recusada'} por {autor.mention}"
        for ref in registro.get("revisao_msgs", []):
            canal = self.bot.get_channel(ref.get("canal_id") or 0)
            if canal is None:
                continue
            try:
                msg = await canal.fetch_message(ref["msg_id"])
                embed = msg.embeds[0].copy() if msg.embeds else discord.Embed()
                embed.color = cor
                embed.add_field(name="Decisão", value=texto, inline=False)
                await msg.edit(embed=embed, view=None)
            except discord.HTTPException:
                continue

    async def aprovar_core(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, canal: discord.TextChannel | None) -> tuple[bool, str]:
        bloqueio = self._bloqueio_decisao(membro_id, autor.id)
        if bloqueio:
            return True, bloqueio
        registro = self.dados[str(membro_id)]

        registro["status"] = "aprovada"
        registro["decidido_por_nome"] = str(autor)
        registro["decidido_por_id"] = autor.id
        registro["decidido_em"] = time.time()
        salvar("whitelist", self.dados)
        registrar_decisao(autor.id, "aprovada")

        membro = guild.get_member(membro_id)
        cargo_sem_acesso = guild.get_role(CARGO_SEM_ACESSO_ID)
        if membro and cargo_sem_acesso and cargo_sem_acesso in membro.roles:
            try:
                await membro.remove_roles(cargo_sem_acesso, reason=f"Whitelist aprovada por {autor}")
            except discord.Forbidden:
                pass

        avisos = []
        respostas = registro.get("respostas", {})
        if membro and respostas.get("rank"):
            try:
                erro = await self.dar_cargo_rank(guild, membro, respostas["rank"])
            except Exception as e:  # a whitelist já está aprovada: não deixa um erro de cargo travar o resto
                _log_erro("dar_cargo_rank", e)
                erro = f"⚠️ Erro inesperado ao dar o cargo de rank: {e}"
            if erro:
                avisos.append(erro)
        if membro and respostas.get("plataforma"):
            try:
                erro = await self.dar_cargo_plataforma(guild, membro, respostas["plataforma"])
            except Exception as e:
                _log_erro("dar_cargo_plataforma", e)
                erro = f"⚠️ Erro inesperado ao dar o cargo de plataforma: {e}"
            if erro:
                avisos.append(erro)
        aviso_extra = ("\n" + "\n".join(avisos)) if avisos else ""

        await self.atualizar_status_board(guild, membro_id)

        mensagem = (
            f"✅ **Whitelist aprovada por {autor.mention}!** "
            f"{membro.mention if membro else ''} os canais do servidor já estão liberados. Bem-vindo(a)! 🚀{aviso_extra}\n"
            f"*(este canal vai ser apagado automaticamente em 10 minutos)*"
        )

        if membro and canal is not None:
            try:
                await canal.set_permissions(membro, overwrite=None)
            except discord.HTTPException:
                pass

        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        return False, mensagem

    async def recusar_core(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, canal: discord.TextChannel | None) -> tuple[bool, str]:
        bloqueio = self._bloqueio_decisao(membro_id, autor.id)
        if bloqueio:
            return True, bloqueio
        registro = self.dados[str(membro_id)]

        registro["status"] = "recusada"
        registro["decidido_por_nome"] = str(autor)
        registro["decidido_por_id"] = autor.id
        registro["decidido_em"] = time.time()
        salvar("whitelist", self.dados)
        registrar_decisao(autor.id, "recusada")

        membro = guild.get_member(membro_id)

        expulso = False
        aviso_kick = ""
        if membro:
            try:
                await membro.kick(reason=f"Whitelist recusada por {autor}")
                expulso = True
                # fica no histórico: se a pessoa voltar, a staff é avisada antes de aceitar
                registrar_punicao_historico(membro_id, "kick", f"Whitelist recusada por {autor}", autor.id)
            except discord.Forbidden:
                aviso_kick = "\n⚠️ Não consegui expulsar o membro (falta permissão/hierarquia de cargo) — remova manualmente."
        else:
            aviso_kick = "\n⚠️ O membro não está mais no servidor."

        await self.atualizar_status_board(guild, membro_id)

        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        quem = membro.mention if membro else "O membro"
        situacao = "foi removido do servidor automaticamente." if expulso else "**não** foi removido do servidor."
        mensagem = (
            f"❌ **Whitelist recusada por {autor.mention}.** "
            f"{quem} {situacao}{aviso_kick}\n"
            f"*(este canal vai ser apagado automaticamente em 10 minutos)*"
        )
        return False, mensagem

    def _membro_id_do_canal(self, canal_id: int) -> int | None:
        for membro_id_str, registro in self.dados.items():
            if registro.get("canal_id") == canal_id:
                return int(membro_id_str)
        return None


    def marcar_cancelada(self, canal_id: int, motivo: str) -> None:
        membro_id = self._membro_id_do_canal(canal_id)
        if membro_id is None:
            return
        registro = self.dados.get(str(membro_id))
        if not registro:
            return
        registro["status"] = "cancelada"
        registro["cancelado_motivo"] = motivo
        registro["cancelado_em"] = time.time()
        salvar("whitelist", self.dados)


    async def pedir_confirmacao_desistencia(self, interaction: discord.Interaction):
        membro_id = self._membro_id_do_canal(interaction.channel.id)
        if membro_id is None or membro_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Só quem tá fazendo essa whitelist pode desistir dela.", ephemeral=True
            )
            return

        registro = self.dados.get(str(membro_id))
        if not registro or registro.get("status") != "em_andamento":
            await interaction.response.send_message(
                "⚠️ Essa whitelist já não tá mais em andamento.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "⚠️ **Tem certeza que quer desistir?** Isso vai fechar e apagar seu canal de whitelist.",
            view=ConfirmarDesistenciaView(membro_id),
            ephemeral=True,
        )

    async def confirmar_desistencia(self, interaction: discord.Interaction, membro_id: int):
        registro = self.dados.get(str(membro_id))
        if not registro:
            await interaction.response.edit_message(content="⚠️ Não encontrei mais essa whitelist.", view=None)
            return

        if registro.get("status") != "em_andamento":
            await interaction.response.edit_message(content="⚠️ Essa whitelist já foi enviada pra análise — não dá mais pra desistir por aqui.", view=None)
            return

        registro["status"] = "cancelada"
        registro["cancelado_motivo"] = "membro"
        registro["cancelado_em"] = time.time()
        salvar("whitelist", self.dados)

        await interaction.response.edit_message(content="🔒 Ok, fechando seu canal em 3 segundos...", view=None)

        canal_id = registro.get("canal_id")
        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal:
            await asyncio.sleep(3)
            try:
                await canal.delete(reason=f"Whitelist cancelada pelo próprio membro ({interaction.user})")
            except discord.HTTPException:
                pass


    @commands.command(name="whitelist")
    @commands.check(_ctx_pode_gerir)
    async def whitelist_manual(self, ctx: commands.Context, membro: discord.Member):
        canal = await self.criar_canal_whitelist(membro)
        await ctx.send(f"✅ Canal de whitelist pronto: {canal.mention}", delete_after=6)

    @whitelist_manual.error
    async def whitelist_manual_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Apenas a **staff da whitelist** (ou administradores) pode usar este comando.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Não achei esse membro.", delete_after=5)


    @commands.command(name="aprovar-whitelist")
    @commands.check(_ctx_pode_gerir)
    async def aprovar_whitelist_cmd(self, ctx: commands.Context):
        await self.fluxo_comando_decisao(ctx, aprovar=True)

    @aprovar_whitelist_cmd.error
    async def aprovar_whitelist_cmd_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Apenas a **staff da whitelist** (ou administradores) pode usar este comando.", delete_after=5)

    @commands.command(name="reprovar-whitelist")
    @commands.check(_ctx_pode_gerir)
    async def reprovar_whitelist_cmd(self, ctx: commands.Context):
        await self.fluxo_comando_decisao(ctx, aprovar=False)

    @reprovar_whitelist_cmd.error
    async def reprovar_whitelist_cmd_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Apenas a **staff da whitelist** (ou administradores) pode usar este comando.", delete_after=5)


    @app_commands.command(name="perfil-whitelist", description="[Staff] Vê o perfil/respostas da whitelist de um membro.")
    @app_commands.describe(membro="Membro cujo perfil de whitelist você quer ver")
    @app_commands.check(_inter_pode_ver_perfil)
    async def perfil_whitelist(self, interaction: discord.Interaction, membro: discord.Member):
        registro = self.dados.get(str(membro.id))
        if not registro:
            await interaction.response.send_message(
                "⚠️ Esse membro ainda não tem uma whitelist registrada.", ephemeral=True
            )
            return

        r = registro.get("respostas", {})
        status_label, status_cor = STATUS_LABELS.get(registro.get("status", "pendente"), ("—", 0x5865F2))

        embed = discord.Embed(
            title=f"📋 Perfil de Whitelist — {membro}",
            color=status_cor,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="Status", value=status_label, inline=True)
        embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
        embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
        embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
        embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
        embed.add_field(name="Maior rank", value=f"{r.get('peak_rank', '—')} ({r.get('peak_div', '—')})", inline=True)
        embed.add_field(name="Conta do maior rank", value=r.get("peak_conta", "—"), inline=True)
        embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
        embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
        embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
        embed.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
        embed.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)
        # e o add_field da pergunta nova aqui tb, esse aqui é o resumo
        # que aparece no comando de consulta manual
        embed.set_footer(text=f"ID: {membro.id}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @perfil_whitelist.error
    async def perfil_whitelist_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Só a **staff** (Membro da Equipe ou staff da whitelist) pode usar esse comando.", ephemeral=True
            )


    @app_commands.command(
        name="editar-whitelist",
        description="[Admin] Cria ou edita a whitelist de um membro na mão (todos os campos do questionário).",
    )
    @app_commands.describe(
        membro="Membro que vai ter a whitelist criada/editada",
        nick="Nick do jogador no Rocket League",
        idioma="Idioma do jogador",
        rank="Rank atual no Rocket League",
        maior_rank="Maior rank já alcançado (peak)",
        peak_div="Divisão do maior rank alcançado",
        peak_conta="O maior rank foi nesta conta ou em outra?",
        plataforma="Plataforma que o jogador usa",
        tempo="Há quanto tempo joga Rocket League",
        microfone="Se o jogador tem microfone",
        ativo="Se o jogador pretende ser ativo na equipe",
        tem_tiktok="Se o jogador tem TikTok",
        tiktok="Usuário ou link do TikTok (se tiver)",
        habilidades="Habilidades extras (texto livre, ex: Designer, Editor de vídeo)",
    )
    @app_commands.choices(
        rank=[app_commands.Choice(name=r, value=r) for r in CARGO_RANKS.keys()],
        idioma=[app_commands.Choice(name=i, value=i) for i in IDIOMAS],
        maior_rank=[app_commands.Choice(name=r, value=r) for r in PEAK_RANKS],
        peak_div=[app_commands.Choice(name=d, value=d) for d in DIVISOES],
        peak_conta=[app_commands.Choice(name=c, value=c) for c in PEAK_CONTAS],
        plataforma=[app_commands.Choice(name=p, value=p) for p in PLATAFORMAS],
        tempo=[app_commands.Choice(name=t, value=t) for t in TEMPOS_JOGANDO],
        microfone=[app_commands.Choice(name="Sim", value="Sim"), app_commands.Choice(name="Não", value="Não")],
        ativo=[app_commands.Choice(name="Sim", value="Sim"), app_commands.Choice(name="Não", value="Não")],
        tem_tiktok=[app_commands.Choice(name="Sim", value="Sim"), app_commands.Choice(name="Não", value="Não")],
    )
    @app_commands.check(_inter_pode_gerir)
    async def editar_whitelist(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        nick: str | None = None,
        idioma: app_commands.Choice[str] | None = None,
        rank: app_commands.Choice[str] | None = None,
        maior_rank: app_commands.Choice[str] | None = None,
        peak_div: app_commands.Choice[str] | None = None,
        peak_conta: app_commands.Choice[str] | None = None,
        plataforma: app_commands.Choice[str] | None = None,
        tempo: app_commands.Choice[str] | None = None,
        microfone: app_commands.Choice[str] | None = None,
        ativo: app_commands.Choice[str] | None = None,
        tem_tiktok: app_commands.Choice[str] | None = None,
        tiktok: str | None = None,
        habilidades: str | None = None,
    ):
        """Comando pensado pra cadastrar/ajustar na mão a whitelist de jogadores
        que entraram antes do sistema existir (ou corrigir dados de quem já
        tem). Cria o registro como 'aprovada' se ainda não existir nenhum."""

        campos = [nick, idioma, rank, maior_rank, peak_div, peak_conta, plataforma, tempo, microfone, ativo, tem_tiktok, tiktok, habilidades]
        if not any(campos):
            await interaction.response.send_message(
                "⚠️ Informe pelo menos um campo pra alterar.",
                ephemeral=True,
            )
            return

        bloqueio = self._bloqueio_analise(self.dados.get(str(membro.id)), interaction.user.id)
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        uid = str(membro.id)
        registro_novo = uid not in self.dados
        registro = self.dados.setdefault(uid, {"respostas": {}, "status": "aprovada"})
        registro.setdefault("respostas", {})

        if registro_novo:
            registro["status"] = "aprovada"
            registro["decidido_por_nome"] = str(interaction.user)
            registro["decidido_por_id"] = interaction.user.id

        avisos = []

        if nick:
            registro["respostas"]["nick"] = nick
            try:
                await membro.edit(nick=nick, reason=f"Whitelist editada manualmente por {interaction.user}")
            except discord.Forbidden:
                avisos.append("⚠️ Não consegui atualizar o apelido do membro (permissão/hierarquia).")

        if idioma:
            registro["respostas"]["idioma"] = idioma.value

        if rank:
            registro["respostas"]["rank"] = rank.value
            erro = await self.dar_cargo_rank(interaction.guild, membro, rank.value)
            if erro:
                avisos.append(erro)

        if maior_rank:
            registro["respostas"]["peak_rank"] = maior_rank.value

        if peak_div:
            registro["respostas"]["peak_div"] = peak_div.value

        if peak_conta:
            registro["respostas"]["peak_conta"] = peak_conta.value

        if maior_rank and maior_rank.value == "Supersonic Legend":
            registro["respostas"]["peak_div"] = "—"

        if plataforma:
            registro["respostas"]["plataforma"] = plataforma.value
            erro = await self.dar_cargo_plataforma(interaction.guild, membro, plataforma.value)
            if erro:
                avisos.append(erro)

        if tempo:
            registro["respostas"]["tempo"] = tempo.value

        if microfone:
            registro["respostas"]["microfone"] = microfone.value

        if ativo:
            registro["respostas"]["ativo"] = ativo.value

        if tem_tiktok:
            registro["respostas"]["tem_tiktok"] = tem_tiktok.value
            if tem_tiktok.value == "Não" and not tiktok:
                registro["respostas"]["tiktok"] = "Não possui"

        if tiktok:
            tiktok_valor, erro_tiktok = normalizar_tiktok(tiktok)
            if erro_tiktok:
                avisos.append(f"⚠️ TikTok não alterado: {erro_tiktok}")
            else:
                registro["respostas"]["tiktok"] = tiktok_valor

        if habilidades:
            registro["respostas"]["habilidades"] = habilidades

        salvar("whitelist", self.dados)

        try:
            await self.atualizar_status_board(interaction.guild, membro.id)
        except discord.HTTPException:
            pass

        r = registro["respostas"]
        embed = discord.Embed(
            title=f"✅ Whitelist {'criada' if registro_novo else 'atualizada'} — {membro}",
            color=0x57F287,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
        embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
        embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
        embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
        embed.add_field(name="Maior rank", value=f"{r.get('peak_rank', '—')} ({r.get('peak_div', '—')})", inline=True)
        embed.add_field(name="Conta do maior rank", value=r.get("peak_conta", "—"), inline=True)
        embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
        embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
        embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
        embed.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
        embed.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)
        embed.set_footer(text=f"Editado por {interaction.user}")

        if avisos:
            embed.add_field(name="⚠️ Avisos", value="\n".join(avisos), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @editar_whitelist.error
    async def editar_whitelist_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Apenas a **staff da whitelist** (ou administradores) pode usar este comando.", ephemeral=True
            )


    # ══════════════════════════════════════════════════════════════════════
    # !policiacivil — reconstrução completa do servidor (Polícia Civil RP)
    #   !policiacivil            → verificação + resumo (libera a confirmação por 5 min)
    #   !policiacivil confirmar  → APAGA tudo e reconstrói
    #   !policiacivil status     → progresso / resultado
    # Só o PROPRIETÁRIO do servidor pode usar. Os dados da estrutura ficam nas
    # constantes _PC_* logo abaixo da classe.
    # ══════════════════════════════════════════════════════════════════════
    @commands.command(name="policiacivil")
    @commands.guild_only()
    async def policiacivil(self, ctx: commands.Context, acao: str = None):
        guild = ctx.guild
        if ctx.author.id != guild.owner_id:
            await ctx.send("❌ Apenas o **proprietário do servidor** pode usar este comando.", delete_after=8)
            return

        acao = (acao or "").lower().strip()
        est = _PC_ESTADO.setdefault(guild.id, _pc_estado_novo())
        lock = _PC_LOCKS.setdefault(guild.id, asyncio.Lock())

        if acao == "status":
            await ctx.send(embed=self._pc_relatorio(guild, est, titulo="📊 Status — !policiacivil"))
            return

        if acao not in ("", "confirmar"):
            await ctx.send("Uso: `!policiacivil` · `!policiacivil confirmar` · `!policiacivil status`")
            return

        if lock.locked():
            await ctx.send("⏳ Já existe uma reconstrução em andamento. Use `!policiacivil status`.")
            return

        # ── verificação de permissões do bot ──
        me = guild.me
        perms = me.guild_permissions
        if not (perms.administrator or (perms.manage_roles and perms.manage_channels)):
            await ctx.send("❌ Eu preciso das permissões **Gerenciar Cargos** e **Gerenciar Canais** (ou Administrador).")
            return

        fase_salva = self._pc_fase_salva(guild.id)
        retomar = fase_salva == "construindo"

        if acao == "":
            est["pendente_ate"] = time.time() + 300
            est["pendente_autor"] = ctx.author.id
            n_canais = sum(len(c[3]) for c in _PC_ESTRUTURA) + len(_PC_VOZ)
            aviso_pos = ""
            if me.top_role.position < 3:
                aviso_pos = (
                    "\n⚠️ Meu cargo está muito embaixo na lista. **Arraste o cargo do bot para o topo** "
                    "(Configurações → Cargos), senão não consigo ordenar a hierarquia."
                )
            if retomar:
                corpo = (
                    "🔁 Uma reconstrução anterior ficou **incompleta**. Ao confirmar, eu **não apago nada de novo**: "
                    "só continuo criando o que faltou, sem duplicar."
                )
            else:
                corpo = (
                    "⚠️ **Ao confirmar, TUDO será apagado:** todas as categorias, canais (texto e voz) e cargos "
                    "personalizados do servidor. Não tem como desfazer.\n"
                    "Ficam preservados: o proprietário, @everyone, cargos de bots/integrações e os cargos que eu mesmo uso."
                )
            await ctx.send(
                "🚔 **Reconstrução — Polícia Civil RP**\n"
                f"{corpo}\n\n"
                f"**Será criado:** {len(_PC_CARGOS)} cargos · {len(_PC_ESTRUTURA) + 1} categorias · {n_canais} canais\n"
                f"{aviso_pos}\n"
                "👉 Para executar, envie `!policiacivil confirmar` em até **5 minutos**."
            )
            return

        # ── acao == "confirmar" ──
        if est.get("pendente_autor") != ctx.author.id or time.time() > est.get("pendente_ate", 0):
            await ctx.send("⚠️ Primeiro envie `!policiacivil` (para ver o resumo) e confirme em até 5 minutos.")
            return
        est["pendente_ate"] = 0

        async with lock:
            est.clear()
            est.update(_pc_estado_novo())
            est["fase"] = "executando"
            est["iniciado"] = time.time()
            est["autor"] = ctx.author.id
            await ctx.send(
                "🚨 **Iniciando!** " + ("Continuando a construção sem apagar." if retomar else
                "Vou apagar a estrutura antiga — este canal também some.")
                + "\nO relatório final vai para o canal **comandos-do-bot** e para a sua DM. Pode levar alguns minutos (respeito os limites da API)."
            )
            try:
                if not retomar:
                    self._pc_salvar_fase(guild.id, "apagando")
                    await self._pc_apagar(guild, est)
                    self._pc_salvar_fase(guild.id, "construindo")
                await self._pc_construir(guild, est)
                self._pc_salvar_fase(guild.id, "concluido")
                est["fase"] = "concluido"
            except Exception as e:
                _log_erro("policiacivil", e)
                est["fase"] = "erro"
                est["falhas"].append(f"Erro inesperado: {str(e)[:200]} (rode `!policiacivil` e confirme de novo para continuar)")
            est["finalizado"] = time.time()
            await self._pc_enviar_relatorio(ctx, guild, est)

    # ── persistência da fase (pra retomar sem apagar de novo) ──
    def _pc_fase_salva(self, guild_id: int):
        try:
            d = ler("policiacivil")
            return (d.get(str(guild_id)) or {}).get("fase") if isinstance(d, dict) else None
        except Exception:
            return None

    def _pc_salvar_fase(self, guild_id: int, fase: str) -> None:
        try:
            d = ler("policiacivil")
            if not isinstance(d, dict):
                d = {}
            d[str(guild_id)] = {"fase": fase, "ts": time.time()}
            salvar("policiacivil", d)
        except Exception as e:
            _log_erro("policiacivil/salvar_fase", e)

    @staticmethod
    def _pc_falha(est: dict, o_que: str, e: BaseException) -> None:
        motivo = getattr(e, "text", None) or str(e) or type(e).__name__
        est["falhas"].append(f"{o_que}: {motivo}"[:300])
        print(f"[POLICIACIVIL] ⚠️ {o_que}: {motivo}")

    # ── 1) apagar a estrutura antiga ──
    async def _pc_apagar(self, guild: discord.Guild, est: dict) -> None:
        me = guild.me
        # canais primeiro (categorias por último, senão os filhos ficam órfãos)
        canais = [c for c in guild.channels if not isinstance(c, discord.CategoryChannel)] + list(guild.categories)
        for c in canais:
            try:
                await c.delete(reason="!policiacivil — reconstrução total")
                est["apagados_canais"] += 1
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                self._pc_falha(est, f"Apagar canal '{c.name}'", e)
            await asyncio.sleep(0.4)

        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            # o Discord não deixa apagar @everyone, cargos gerenciados (bots/integrações) nem
            # cargos acima do meu; e os cargos que eu uso ficam, senão perco as permissões
            if r.is_default() or r.managed or r in me.roles or r.position >= me.top_role.position:
                continue
            try:
                await r.delete(reason="!policiacivil — reconstrução total")
                est["apagados_cargos"] += 1
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                self._pc_falha(est, f"Apagar cargo '{r.name}'", e)
            await asyncio.sleep(0.4)

    # ── 2) construir (idempotente: reaproveita o que já existe) ──
    async def _pc_construir(self, guild: discord.Guild, est: dict) -> None:
        mapa: dict[str, discord.Role] = {}

        for key, nome, cor, perms, hoist in _PC_CARGOS:
            role = _pc_achar(guild.roles, nome)
            if role is not None:
                mapa[key] = role
                est["cargos_existentes"] += 1
                continue
            try:
                mapa[key] = await guild.create_role(
                    name=nome,
                    colour=discord.Colour(int(cor, 16)),
                    permissions=discord.Permissions(**perms),
                    hoist=hoist,
                    mentionable=False,
                    reason="!policiacivil",
                )
                est["cargos_criados"] += 1
            except discord.HTTPException as e:
                self._pc_falha(est, f"Criar cargo '{nome}'", e)
            await asyncio.sleep(0.5)

        # hierarquia: a ordem da lista _PC_CARGOS é de cima pra baixo, logo abaixo do cargo do bot
        ordem = [mapa[k] for k, *_ in _PC_CARGOS if k in mapa]
        topo = guild.me.top_role.position - 1
        try:
            posicoes = {r: max(1, topo - i) for i, r in enumerate(ordem)}
            if hasattr(guild, "edit_role_positions"):
                await guild.edit_role_positions(positions=posicoes, reason="!policiacivil — hierarquia")
            else:
                for r, p in posicoes.items():
                    await r.edit(position=p, reason="!policiacivil — hierarquia")
                    await asyncio.sleep(0.4)
            est["hierarquia_ok"] = True
        except discord.HTTPException as e:
            self._pc_falha(est, "Ordenar hierarquia (arraste o cargo do bot para o topo e rode de novo)", e)

        # categorias + canais de texto
        for cat_nome, view, write, canais in _PC_ESTRUTURA:
            cat = await self._pc_categoria(guild, est, mapa, cat_nome, view, False)
            if cat is None:
                continue
            for item in canais:
                if isinstance(item, str):
                    nome, v_ov, w_ov = item, None, None
                else:
                    nome, v_ov, w_ov = item
                v = view if v_ov is None else v_ov
                w = (write if v_ov is None else None) if w_ov is None else w_ov
                await self._pc_canal(guild, est, mapa, cat, nome, v, w, False)

        # salas de voz
        cat_voz = await self._pc_categoria(guild, est, mapa, _PC_CATEGORIA_VOZ, [], True)
        if cat_voz is not None:
            for nome, view in _PC_VOZ:
                await self._pc_canal(guild, est, mapa, cat_voz, nome, view, None, True)

    async def _pc_categoria(self, guild, est, mapa, nome, view, voz):
        ow = self._pc_overwrites(guild, mapa, view, [] if not voz else None, voz)
        cat = _pc_achar(guild.categories, nome)
        try:
            if cat is None:
                cat = await guild.create_category(name=nome, overwrites=ow, reason="!policiacivil")
                est["categorias_criadas"] += 1
            else:
                await cat.edit(overwrites=ow, reason="!policiacivil — permissões")
                est["categorias_existentes"] += 1
            est["permissoes"] += len(ow)
            est["perm_categorias"] += 1
            await asyncio.sleep(0.5)
            return cat
        except discord.HTTPException as e:
            self._pc_falha(est, f"Categoria '{nome}'", e)
            return None

    async def _pc_canal(self, guild, est, mapa, cat, nome, view, write, voz):
        ow = self._pc_overwrites(guild, mapa, view, write, voz)
        existente = _pc_achar(cat.voice_channels if voz else cat.text_channels, nome)
        try:
            if existente is None:
                if voz:
                    await guild.create_voice_channel(name=nome, category=cat, overwrites=ow, reason="!policiacivil")
                else:
                    await guild.create_text_channel(name=nome, category=cat, overwrites=ow, reason="!policiacivil")
                est["canais_criados"] += 1
            else:
                await existente.edit(overwrites=ow, reason="!policiacivil — permissões")
                est["canais_existentes"] += 1
            est["permissoes"] += len(ow)
            est["perm_canais"] += 1
        except discord.HTTPException as e:
            self._pc_falha(est, f"Canal '{nome}'", e)
        await asyncio.sleep(0.5)

    @staticmethod
    def _pc_overwrites(guild: discord.Guild, mapa: dict, view, write, voz: bool = False) -> dict:
        """Permissões EXPLÍCITAS por canal (nada de depender só de esconder o nome).
        view  = quem enxerga (aceita "@everyone")
        write = quem escreve (None = mesmo grupo de view; [] = ninguém além do comando/admin)
        Chefe, Subchefe e Administrador do Servidor sempre enxergam e escrevem."""
        view = list(view or [])
        write = view if write is None else list(write)
        publico = "@everyone" in view
        ow: dict = {}
        if voz:
            ow[guild.default_role] = discord.PermissionOverwrite(view_channel=False, connect=False)
        elif publico:
            ow[guild.default_role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=False, add_reactions=False,
                create_public_threads=False, create_private_threads=False,
            )
        else:
            ow[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        # o próprio bot sempre precisa enxergar/escrever (relatórios e outras cogs)
        ow[guild.me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            embed_links=True, attach_files=True, manage_messages=True, connect=True, speak=True,
        )
        for k in dict.fromkeys(view + write + _PC_AUTO):
            if k == "@everyone":
                continue
            role = mapa.get(k)
            if role is None:
                continue
            pode = k in write or k in _PC_AUTO
            if voz:
                ow[role] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
            else:
                ow[role] = discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=pode,
                    add_reactions=True, embed_links=pode, attach_files=pode,
                )
        return ow

    # ── relatório ──
    def _pc_relatorio(self, guild: discord.Guild, est: dict, titulo: str = "🚔 Relatório — Polícia Civil RP") -> discord.Embed:
        fase = est.get("fase", "ocioso")
        cor = {"concluido": 0x57F287, "erro": 0xED4245, "executando": 0xFEE75C}.get(fase, 0x5865F2)
        embed = discord.Embed(title=titulo, color=cor)
        embed.description = f"**Fase:** {fase}" + (f" · salva: {self._pc_fase_salva(guild.id) or '—'}")
        embed.add_field(name="🧹 Apagados", value=f"Canais/categorias: {est['apagados_canais']}\nCargos: {est['apagados_cargos']}", inline=True)
        embed.add_field(name="🛡️ Cargos", value=f"Criados: {est['cargos_criados']}\nJá existiam: {est['cargos_existentes']}\nHierarquia: {'✅' if est['hierarquia_ok'] else '⚠️ não ordenada'}", inline=True)
        embed.add_field(name="📂 Categorias", value=f"Criadas: {est['categorias_criadas']}\nJá existiam: {est['categorias_existentes']}", inline=True)
        embed.add_field(name="💬 Canais", value=f"Criados: {est['canais_criados']}\nJá existiam: {est['canais_existentes']}", inline=True)
        embed.add_field(
            name="🔐 Permissões configuradas",
            value=(
                f"{est['permissoes']} overwrites explícitos em {est['perm_categorias']} categorias e {est['perm_canais']} canais.\n"
                "Canais privados escondidos de @everyone com acesso só aos cargos autorizados; "
                "Chefe/Subchefe/Administrador em todos. Permissões de servidor: Chefia (moderação), "
                "Administrador (gestão técnica, **sem** Administrador), Bots (só envio básico)."
            ),
            inline=False,
        )
        falhas = est.get("falhas", [])
        if falhas:
            texto = "\n".join(f"• {f}" for f in falhas[:10])
            if len(falhas) > 10:
                texto += f"\n… e mais {len(falhas) - 10}"
            embed.add_field(name=f"❌ Falhas ({len(falhas)})", value=texto[:1024], inline=False)
        else:
            embed.add_field(name="❌ Falhas", value="Nenhuma", inline=False)
        if est.get("iniciado") and est.get("finalizado"):
            embed.set_footer(text=f"Duração: {int(est['finalizado'] - est['iniciado'])}s")
        return embed

    async def _pc_enviar_relatorio(self, ctx: commands.Context, guild: discord.Guild, est: dict) -> None:
        embed = self._pc_relatorio(guild, est)
        enviado = False
        destino = _pc_achar(guild.text_channels, "🤖・comandos-do-bot")
        for canal in (destino, ctx.channel):
            if canal is None or enviado:
                continue
            try:
                await canal.send(content=f"<@{est.get('autor')}>", embed=embed,
                                 allowed_mentions=discord.AllowedMentions(users=True))
                enviado = True
            except discord.HTTPException:
                continue  # o canal pode ter sido apagado
        try:
            await ctx.author.send(embed=embed)
        except discord.HTTPException:
            pass

    # ══════════════════════════════════════════════════════════════════════
    # !pconlycargos — mexe SÓ nos cargos (canais e categorias ficam como estão):
    #   apaga todos os cargos comuns, recria os da Polícia Civil com cor,
    #   permissões e hierarquia. Só o proprietário do servidor.
    # ══════════════════════════════════════════════════════════════════════
    @commands.command(name="pconlycargos")
    @commands.guild_only()
    async def pconlycargos(self, ctx: commands.Context):
        guild = ctx.guild
        if ctx.author.id != guild.owner_id:
            await ctx.send("❌ Apenas o **proprietário do servidor** pode usar este comando.", delete_after=8)
            return
        if not (guild.me.guild_permissions.administrator or guild.me.guild_permissions.manage_roles):
            await ctx.send("❌ Eu preciso da permissão **Gerenciar Cargos** (ou Administrador).")
            return
        lock = _PC_LOCKS.setdefault(guild.id, asyncio.Lock())
        if lock.locked():
            await ctx.send("⏳ Já existe uma operação em andamento. Use `!policiacivil status`.")
            return

        async with lock:
            est = _pc_estado_novo()
            est["fase"] = "executando"
            est["iniciado"] = time.time()
            est["autor"] = ctx.author.id
            _PC_ESTADO[guild.id] = est
            aviso = await ctx.send("⏳ Apagando os cargos antigos e recriando os da Polícia Civil... (canais não serão alterados)")
            try:
                await self._pc_apagar_cargos(guild, est)
                await self._pc_criar_cargos(guild, est)
                est["fase"] = "concluido"
            except Exception as e:
                _log_erro("pconlycargos", e)
                est["fase"] = "erro"
                est["falhas"].append(f"Erro inesperado: {str(e)[:200]}")
            est["finalizado"] = time.time()

            embed = discord.Embed(
                title="🛡️ Relatório — só cargos",
                color={"concluido": 0x57F287, "erro": 0xED4245}.get(est["fase"], 0x5865F2),
            )
            embed.add_field(name="🧹 Cargos apagados", value=str(est["apagados_cargos"]), inline=True)
            embed.add_field(name="✅ Cargos criados", value=str(est["cargos_criados"]), inline=True)
            embed.add_field(name="📶 Hierarquia", value="✅ ordenada" if est["hierarquia_ok"] else "⚠️ não ordenada", inline=True)
            embed.add_field(
                name="🔐 Permissões",
                value=(
                    "Chefia: moderação · Gestão (Adjunto→Delegado): mensagens/voz · Corregedoria: mensagens · "
                    "Administrador do Servidor: gestão técnica (sem Administrador) · Bots: envio básico · demais: sem extras."
                ),
                inline=False,
            )
            falhas = est["falhas"]
            if falhas:
                texto = "\n".join(f"• {f}" for f in falhas[:10])
                if len(falhas) > 10:
                    texto += f"\n… e mais {len(falhas) - 10}"
                embed.add_field(name=f"❌ Falhas ({len(falhas)})", value=texto[:1024], inline=False)
            else:
                embed.add_field(name="❌ Falhas", value="Nenhuma", inline=False)
            embed.set_footer(text=f"Duração: {int(est['finalizado'] - est['iniciado'])}s")
            try:
                await aviso.edit(content=None, embed=embed)
            except discord.HTTPException:
                await ctx.send(embed=embed)

    async def _pc_apagar_cargos(self, guild: discord.Guild, est: dict) -> None:
        me = guild.me
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            # fora: @everyone, cargos de bots/integrações, os cargos que o bot usa e os acima do dele
            if r.is_default() or r.managed or r in me.roles or r.position >= me.top_role.position:
                continue
            try:
                await r.delete(reason="!pconlycargos — recriando cargos")
                est["apagados_cargos"] += 1
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                self._pc_falha(est, f"Apagar cargo '{r.name}'", e)
            await asyncio.sleep(0.4)

    async def _pc_criar_cargos(self, guild: discord.Guild, est: dict) -> None:
        criados: list[discord.Role] = []
        for key, nome, cor, perms, hoist in _PC_CARGOS:
            role = _pc_achar(guild.roles, nome)  # se sobrou algum igual (não deu pra apagar), reaproveita
            try:
                if role is None:
                    role = await guild.create_role(
                        name=nome, colour=discord.Colour(int(cor, 16)),
                        permissions=discord.Permissions(**perms), hoist=hoist,
                        mentionable=False, reason="!pconlycargos",
                    )
                    est["cargos_criados"] += 1
                else:
                    await role.edit(
                        colour=discord.Colour(int(cor, 16)), permissions=discord.Permissions(**perms),
                        hoist=hoist, reason="!pconlycargos — ajustando",
                    )
                    est["cargos_existentes"] += 1
                criados.append(role)
            except discord.HTTPException as e:
                self._pc_falha(est, f"Criar cargo '{nome}'", e)
            await asyncio.sleep(0.5)

        # hierarquia: ordem da lista _PC_CARGOS (de cima pra baixo), logo abaixo do cargo do bot
        topo = guild.me.top_role.position - 1
        try:
            posicoes = {r: max(1, topo - i) for i, r in enumerate(criados)}
            if hasattr(guild, "edit_role_positions"):
                await guild.edit_role_positions(positions=posicoes, reason="!pconlycargos — hierarquia")
            else:
                for r, p in posicoes.items():
                    await r.edit(position=p, reason="!pconlycargos — hierarquia")
                    await asyncio.sleep(0.4)
            est["hierarquia_ok"] = True
        except discord.HTTPException as e:
            self._pc_falha(est, "Ordenar hierarquia (arraste o cargo do bot para o topo e rode de novo)", e)


# ── dados do !policiacivil ────────────────────────────────────────────────
_PC_ESTADO: dict = {}
_PC_LOCKS: dict = {}


def _pc_estado_novo() -> dict:
    return {
        "fase": "ocioso", "iniciado": None, "finalizado": None, "autor": None,
        "pendente_ate": 0, "pendente_autor": None,
        "apagados_canais": 0, "apagados_cargos": 0,
        "cargos_criados": 0, "cargos_existentes": 0, "hierarquia_ok": False,
        "categorias_criadas": 0, "categorias_existentes": 0,
        "canais_criados": 0, "canais_existentes": 0,
        "permissoes": 0, "perm_categorias": 0, "perm_canais": 0,
        "falhas": [],
    }


def _pc_norm(texto: str) -> str:
    # o Discord remove o seletor de emoji (U+FE0F) e põe minúsculas nos canais de texto
    return texto.replace("️", "").strip().lower()


def _pc_achar(itens, nome: str):
    alvo = _pc_norm(nome)
    return next((i for i in itens if _pc_norm(i.name) == alvo), None)


# permissões de servidor (nada de Administrador pra policial/divisão)
_PC_P_CHEFIA = dict(manage_messages=True, moderate_members=True, manage_nicknames=True,
                    mention_everyone=True, move_members=True, mute_members=True)
_PC_P_GESTAO = dict(manage_messages=True, move_members=True, mute_members=True)
_PC_P_CORREG = dict(manage_messages=True)
_PC_P_ADMIN = dict(manage_guild=True, manage_roles=True, manage_channels=True, manage_messages=True,
                   manage_nicknames=True, kick_members=True, ban_members=True, moderate_members=True,
                   view_audit_log=True, manage_webhooks=True, mention_everyone=True)
_PC_P_BOTS = dict(send_messages=True, embed_links=True, attach_files=True, read_message_history=True,
                  add_reactions=True, use_external_emojis=True)

# (chave, nome, cor HEX, permissões, hoist) — ordem = de CIMA pra BAIXO na hierarquia
_PC_CARGOS = [
    ("chefe",        "👑 Chefe da Polícia Civil",        "8B0000", _PC_P_CHEFIA, True),
    ("subchefe",     "💠 Subchefe da Polícia Civil",     "B22222", _PC_P_CHEFIA, True),
    ("adjunto",      "🏛️ Delegado-Geral Adjunto",        "800080", _PC_P_GESTAO, True),
    ("diretor",      "🎖️ Diretor de Departamento",       "9932CC", _PC_P_GESTAO, True),
    ("titular",      "⚖️ Delegado Titular",              "FF0000", _PC_P_GESTAO, True),
    ("delegado",     "🦅 Delegado",                      "D32F2F", _PC_P_GESTAO, True),
    ("inv_chefe",    "🔎 Investigador-Chefe",            "1565C0", {}, True),
    ("investigador", "🕵️ Investigador",                  "1976D2", {}, True),
    ("escrivao",     "📑 Escrivão",                      "00838F", {}, True),
    ("agente",       "🚔 Agente de Polícia",             "00A6A6", {}, True),
    ("perito",       "🧬 Perito Criminal",               "6A1B9A", {}, True),
    ("instrutor",    "🎓 Instrutor da Academia",         "2E7D32", {}, True),
    ("aluno",        "📚 Aluno da Academia",             "43A047", {}, True),
    ("corregedoria", "🛡️ Corregedoria",                  "795548", _PC_P_CORREG, True),
    ("admin",        "⚙️ Administrador do Servidor",     "607D8B", _PC_P_ADMIN, True),
    # divisões (só identificam o departamento, sem poder administrativo)
    ("dpc",          "🏢 DPC — Departamento de Polícia Civil",   "263238", {}, False),
    ("dhpp",         "🕵️ DHPP — Homicídios e Proteção à Pessoa", "8E0000", {}, False),
    ("denarc",       "💊 DENARC — Narcóticos",                   "6A1B9A", {}, False),
    ("core",         "🚨 CORE — Operações Especiais",            "212121", {}, False),
    ("inteligencia", "🧠 Inteligência Policial",                 "0D47A1", {}, False),
    ("ptc",          "🔬 Polícia Técnico-Científica",            "00838F", {}, False),
    ("dep_op",       "🚔 Departamento Operacional",              "1565C0", {}, False),
    ("dep_inv",      "📂 Departamento de Investigação",          "283593", {}, False),
    ("dep_adm",      "📋 Departamento Administrativo",           "546E7A", {}, False),
    ("academia",     "🎓 Academia de Polícia",                   "2E7D32", {}, False),
    ("assuntos",     "⚖️ Assuntos Internos",                     "795548", {}, False),
    # funcionais / serviço
    ("servico",      "🟢 Em Serviço",                  "2E7D32", {}, False),
    ("fora",         "🔴 Fora de Serviço",             "C62828", {}, False),
    ("licenca",      "🌴 Licença",                     "78909C", {}, False),
    ("treino",       "📌 Em Treinamento",              "F9A825", {}, False),
    ("destaque",     "⭐ Destaque do Mês",             "FFD700", {}, False),
    ("pmes",         "🏆 Policial do Mês",             "FF8F00", {}, False),
    ("recrutador",   "📨 Recrutador",                  "00897B", {}, False),
    ("avaliador",    "📝 Avaliador",                   "3949AB", {}, False),
    ("plantao",      "🔊 Responsável pelo Plantão",    "0277BD", {}, False),
    # base
    ("bots",         "🤖 Bots",                        "808080", _PC_P_BOTS, False),
    ("cidadao",      "👤 Cidadão",                     "BDBDBD", {}, False),
]

# grupos de acesso
_PC_AUTO = ["chefe", "subchefe", "admin"]            # enxergam e escrevem em tudo
_PC_TOP = ["chefe", "subchefe", "adjunto", "diretor"]
_PC_GEST = _PC_TOP + ["titular", "delegado"]
_PC_POL = _PC_GEST + ["inv_chefe", "investigador", "escrivao", "agente", "perito"]
_PC_INV = _PC_GEST + ["inv_chefe", "investigador", "escrivao", "perito", "dhpp", "denarc", "inteligencia", "dep_inv"]
_PC_GERAL = ["cidadao", "aluno", "instrutor"] + _PC_POL

_PC_RECR = ["cidadao", "recrutador", "avaliador"]
_PC_TREINO = ["aluno", "instrutor", "academia"]
_PC_ATEND = _PC_POL + ["cidadao"]

# (categoria, quem vê, quem escreve, canais)
#   quem escreve: None = igual a "quem vê" · [] = só comando/admin
#   canal = "nome"  ou  (nome, view|None, write|None)  p/ sobrescrever o padrão da categoria
_PC_ESTRUTURA = [
    ("📌・CENTRAL DE INFORMAÇÕES", ["@everyone"], [], [
        "👋・boas-vindas", "📜・regulamento", "📢・anúncios-oficiais", "🏅・hierarquia-policial",
        "🏢・departamentos", ("❓・dúvidas", None, _PC_GERAL), "📋・como-ingressar",
        ("🤖・comandos-do-bot", None, _PC_GERAL + ["bots"]),
    ]),
    ("📝・RECRUTAMENTO", _PC_RECR, ["recrutador", "avaliador"], [
        ("📋・inscrições", None, _PC_RECR), ("📑・fichas-de-candidatura", None, _PC_RECR),
        ("🎙️・agendamento-de-entrevistas", None, _PC_RECR), ("🧠・provas-teóricas", None, _PC_RECR),
        "📊・resultados", "✅・aprovados", "❌・reprovados",
        ("🔒・equipe-de-recrutamento", ["recrutador", "avaliador"], None),
    ]),
    ("🏛️・COMANDO-GERAL", _PC_TOP, None, [
        "📢・comunicados-do-comando", "📅・reuniões", "📊・relatórios-de-gestão",
        "📈・promoções-e-rebaixamentos", "📋・ordens-de-serviço", "🗳️・decisões-administrativas",
        ("🔒・reunião-privada", [], None),
    ]),
    ("🚔・OPERAÇÕES POLICIAIS", _PC_POL + ["core", "dep_op"], None, [
        "🚨・acionamentos", "📍・operações-em-andamento", "📋・planejamento-operacional", "🚓・patrulhamento",
        "📡・comunicação-operacional", "📝・relatórios-operacionais", "📂・operações-concluídas",
    ]),
    ("🔎・INVESTIGAÇÕES", _PC_INV, None, [
        "🚨・novas-ocorrências", "📁・casos-em-andamento", "📝・relatórios-investigativos",
        "🔬・provas-e-evidências", "📂・casos-arquivados",
        ("🔒・casos-confidenciais", ["adjunto", "diretor", "titular", "delegado", "inv_chefe"], None),
        "🧾・depoimentos", "📋・mandados-e-intimações",
    ]),
    ("⚖️・DELEGACIA", _PC_POL, None, [
        ("📄・boletins-de-ocorrência", _PC_ATEND, _PC_ATEND),
        ("📨・intimações", _PC_ATEND, _PC_POL),
        "🗂️・inquéritos-policiais", "📋・registro-de-ocorrências",
        ("👥・atendimento-ao-cidadão", _PC_ATEND, _PC_ATEND),
        "🚔・plantão-policial", "📝・termos-e-depoimentos",
    ]),
    ("🕵️・DHPP", ["dhpp"] + _PC_TOP, None, [
        "📂・casos-de-homicídio", "🔎・investigações-de-pessoas", "📝・relatórios-dhpp",
        ("🔒・arquivo-dhpp", ["dhpp"], None),
    ]),
    ("💊・DENARC", ["denarc"] + _PC_TOP, None, [
        "📂・casos-denarc", "🔎・investigações-de-narcóticos", "📝・relatórios-denarc",
        ("🔒・arquivo-denarc", ["denarc"], None),
    ]),
    ("🚨・CORE", ["core"] + _PC_TOP, None, [
        "📢・comunicados-core", "🎯・planejamento-tático", "📋・missões-especiais", "📝・relatórios-core",
        ("🔒・sala-restrita-core", ["core"], None),
    ]),
    ("🧠・INTELIGÊNCIA", ["inteligencia"] + _PC_TOP, None, [
        "📡・informações-de-inteligência", "🔎・análise-de-informações", "📋・relatórios-de-inteligência",
        ("🔒・arquivo-confidencial", ["inteligencia"], None),
    ]),
    ("🔬・POLÍCIA TÉCNICO-CIENTÍFICA", ["ptc", "perito", "titular"] + _PC_TOP, None, [
        "🧪・perícias", "🔬・análise-de-evidências", "📑・laudos-periciais", "📂・arquivo-pericial",
    ]),
    ("🎓・ACADEMIA DE POLÍCIA", _PC_TREINO + _PC_TOP, ["instrutor", "academia"], [
        "📚・materiais-de-estudo", "📖・legislação-do-rp",
        ("🎯・treinamentos", None, _PC_TREINO), ("📝・avaliações", None, _PC_TREINO),
        "🏅・certificações", "📊・desempenho-dos-alunos",
        ("🔒・instrutores", ["instrutor", "academia"], None),
    ]),
    ("🛡️・CORREGEDORIA", ["corregedoria", "assuntos"], None, [
        "📩・denúncias-internas", "⚖️・processos-disciplinares", "📝・apuração-de-conduta",
        "📂・processos-arquivados", "🔒・reunião-da-corregedoria",
    ]),
    ("📋・ADMINISTRAÇÃO", _PC_TOP, None, [
        "👥・gestão-de-membros", "🪪・atribuição-de-cargos", "📊・estatísticas", "🧾・registro-de-alterações",
        ("🛠️・configuração-do-servidor", ["admin"], None),
        ("🔒・administração-privada", ["admin"], None),
    ]),
    ("🏆・MÉRITO POLICIAL", _PC_GERAL, _PC_TOP, [
        "⭐・destaques-do-mês", "🏆・policial-do-mês", "🎖️・condecorações", "📜・histórico-de-promoções",
    ]),
    ("💬・CONVIVÊNCIA", _PC_GERAL, None, [
        "💭・chat-geral", "📸・fotos-e-clipes", "😂・memes", "💡・sugestões", "📮・suporte",
        ("🤖・comandos-de-bots", _PC_GERAL + ["bots"], None),
    ]),
]

_PC_CATEGORIA_VOZ = "🔊・SALAS DE VOZ"
_PC_VOZ = [
    ("⏳・Sala de Espera", _PC_GERAL),
    ("👑・Comando-Geral", _PC_TOP),
    ("🚔・Operacional", _PC_POL + ["core", "dep_op"]),
    ("📡・Comunicação Policial", _PC_POL),
    ("🔎・Investigações", _PC_INV),
    ("🎓・Treinamento", _PC_TREINO),
    ("🎙️・Entrevistas", _PC_RECR),
    ("🛡️・Corregedoria", ["corregedoria", "assuntos"]),
    ("🧠・Inteligência", ["inteligencia"]),
    ("🚨・CORE", ["core"]),
    ("💬・Convivência", _PC_GERAL),
]


# ══════════════════════════════════════════════════════════════════════════
#  SISTEMA DA POLÍCIA CIVIL — !setap
#  Cog separada (PoliciaSistema) porque os botões precisam ser registrados na
#  inicialização do bot. Cria/atualiza os canais funcionais e publica os painéis.
# ══════════════════════════════════════════════════════════════════════════
import io
from datetime import timedelta

_PS_COR = 0x1565C0
_PS_LIMITE_PONTO = 12 * 3600          # turno esquecido aberto é encerrado após 12h
_PS_NOMES = {k: n for k, n, *_ in _PC_CARGOS}
_PS_STAFF_TICKET = _PC_POL + ["plantao"]
_PS_ESCADA = ["agente", "investigador", "inv_chefe", "delegado", "titular", "diretor", "adjunto", "subchefe"]

_PS_CAT_CENTRAL = "📌・CENTRAL DE INFORMAÇÕES"
_PS_CAT_REC = "📝・RECRUTAMENTO"
_PS_CAT_COMANDO = "🏛️・COMANDO-GERAL"
_PS_CAT_OPS = "🚔・OPERAÇÕES POLICIAIS"
_PS_CAT_DELEG = "⚖️・DELEGACIA"
_PS_CAT_CONV = "💬・CONVIVÊNCIA"
_PS_CAT_PONTO = "🕒・PONTO E SERVIÇO"
_PS_CAT_TICKETS = "🎫・ATENDIMENTOS"
_PS_CAT_LOGS = "🛠️・LOGS"

# categorias que o !setap cria se não existirem: nome -> quem vê
_PS_CATEGORIAS_NOVAS = {
    _PS_CAT_PONTO: _PC_POL,
    _PS_CAT_TICKETS: _PS_STAFF_TICKET,
    _PS_CAT_LOGS: _PC_TOP,
}

# (chave, categoria, nome do canal, quem vê, quem escreve)
# Canais que já existem (criados pelo !policiacivil) são reaproveitados pelo nome.
_PS_CANAIS = [
    ("boas_vindas",   _PS_CAT_CENTRAL, "👋・boas-vindas",               ["@everyone"], []),
    ("saidas",        _PS_CAT_CENTRAL, "🚪・saídas",                    _PC_GERAL, []),
    ("regulamento",   _PS_CAT_CENTRAL, "📜・regulamento",               ["@everyone"], []),
    ("hierarquia",    _PS_CAT_CENTRAL, "🏅・hierarquia-policial",       ["@everyone"], []),
    ("departamentos", _PS_CAT_CENTRAL, "🏢・departamentos",             ["@everyone"], []),
    ("como_ingressar", _PS_CAT_CENTRAL, "📋・como-ingressar",           ["@everyone"], []),
    ("comandos",      _PS_CAT_CENTRAL, "🤖・comandos-do-bot",           ["@everyone"], _PC_GERAL + ["bots"]),
    ("rec_painel",    _PS_CAT_REC,     "📋・inscrições",                _PC_RECR, []),
    ("rec_equipe",    _PS_CAT_REC,     "🔒・equipe-de-recrutamento",    ["recrutador", "avaliador"], None),
    ("aprovados",     _PS_CAT_REC,     "✅・aprovados",                 _PC_RECR, []),
    ("reprovados",    _PS_CAT_REC,     "❌・reprovados",                _PC_RECR, []),
    ("promocoes",     _PS_CAT_COMANDO, "📈・promoções-e-rebaixamentos", _PC_TOP, []),
    ("acionamentos",  _PS_CAT_OPS,     "🚨・acionamentos",              _PC_POL + ["core", "dep_op"], []),
    ("oc_painel",     _PS_CAT_DELEG,   "📋・registro-de-ocorrências",   _PC_POL, []),
    ("oc_log",        _PS_CAT_DELEG,   "📂・ocorrências-registradas",   _PC_POL, []),
    ("bo_painel",     _PS_CAT_DELEG,   "📄・boletins-de-ocorrência",    _PC_ATEND, []),
    ("bo_recebidos",  _PS_CAT_DELEG,   "📥・boletins-recebidos",        _PC_POL, []),
    ("tk_painel",     _PS_CAT_DELEG,   "👥・atendimento-ao-cidadão",    _PC_ATEND, []),
    ("sugestoes",     _PS_CAT_CONV,    "💡・sugestões",                 _PC_GERAL, _PC_GERAL),
    ("ponto",         _PS_CAT_PONTO,   "🕒・bater-ponto",               _PC_POL, []),
    ("ponto_log",     _PS_CAT_PONTO,   "🧾・registro-de-ponto",         _PC_POL, []),
    ("ranking",       _PS_CAT_PONTO,   "🏆・ranking-de-horas",          _PC_POL, []),
    ("log_tk",        _PS_CAT_LOGS,    "🗃️・logs-de-atendimento",       _PC_TOP, []),
    ("log_membros",   _PS_CAT_LOGS,    "🚪・entradas-e-saídas",         _PC_TOP, []),
    ("log_msg",       _PS_CAT_LOGS,    "📨・logs-de-mensagens",         _PC_TOP, []),
    ("log_voz",       _PS_CAT_LOGS,    "🎙️・logs-de-voz",               _PC_TOP, []),
    ("log_cargos",    _PS_CAT_LOGS,    "🛡️・logs-de-cargos",            _PC_TOP, []),
    ("log_mod",       _PS_CAT_LOGS,    "🔨・logs-de-moderação",         _PC_TOP, []),
]

_PS_TICKET_TIPOS = {
    "denuncia":    ("Denúncia", "🚨", "Relatar um crime ou situação suspeita"),
    "duvida":      ("Dúvida", "❓", "Tirar dúvidas com a corporação"),
    "solicitacao": ("Solicitação", "📨", "Pedir um serviço ou documento"),
    "elogio":      ("Elogio / Sugestão", "💬", "Elogiar ou sugerir melhorias"),
    "outro":       ("Outro assunto", "🎫", "Qualquer outro assunto"),
}

_PS_DEPARTAMENTOS = [
    ("dpc", "Sede e comando administrativo da corporação."),
    ("dhpp", "Investiga homicídios e crimes contra a pessoa."),
    ("denarc", "Combate ao tráfico e aos crimes de narcóticos."),
    ("core", "Operações especiais e intervenções táticas de alto risco."),
    ("inteligencia", "Análise de informações e inteligência policial."),
    ("ptc", "Perícias, análise de provas e laudos técnicos."),
    ("dep_op", "Policiamento ostensivo e atendimento a ocorrências."),
    ("dep_inv", "Investigação de casos e condução de inquéritos."),
    ("dep_adm", "Gestão administrativa, documentos e pessoal."),
    ("academia", "Formação e treinamento de novos policiais."),
    ("assuntos", "Apuração de conduta e processos disciplinares."),
]

_PS_HIERARQUIA = ["chefe", "subchefe", "adjunto", "diretor", "titular", "delegado", "inv_chefe",
                  "investigador", "escrivao", "agente", "perito", "instrutor", "aluno", "corregedoria"]


def _ps_dur(seg: float) -> str:
    seg = max(0, int(seg))
    if seg < 60:
        return f"{seg}s"
    h, r = divmod(seg, 3600)
    m = r // 60
    return f"{h}h{m:02d}min" if h else f"{m}min"


def _ps_txt(valor, limite: int = 1000) -> str:
    t = discord.utils.escape_mentions(str(valor or "").strip()) or "—"
    return t if len(t) <= limite else t[: limite - 1] + "…"


def _ps_set_field(embed: discord.Embed, nome: str, valor: str, inline: bool = True) -> None:
    for i, f in enumerate(embed.fields):
        if f.name == nome:
            embed.set_field_at(i, name=nome, value=valor, inline=inline)
            return
    embed.add_field(name=nome, value=valor, inline=inline)


def _ps_cog(interaction: discord.Interaction) -> "PoliciaSistema":
    return interaction.client.get_cog("PoliciaSistema")


class _PSView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        _log_erro(type(self).__name__, error)
        await _responder(interaction, "⚠️ Algo deu errado. Tente de novo; se persistir, chame a staff.", ephemeral=True)


class _PSModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        _log_erro(type(self).__name__, error)
        await _responder(interaction, "⚠️ Não consegui enviar. Tente de novo.", ephemeral=True)


# ── modais ────────────────────────────────────────────────────────────────
class OcorrenciaModal(_PSModal, title="Registrar ocorrência"):
    tipo = discord.ui.TextInput(label="Tipo da ocorrência", placeholder="Ex: Roubo, Tráfico, Acidente", max_length=60)
    local = discord.ui.TextInput(label="Local", max_length=100)
    envolvidos = discord.ui.TextInput(label="Envolvidos", style=discord.TextStyle.paragraph, required=False, max_length=500)
    descricao = discord.ui.TextInput(label="Descrição dos fatos", style=discord.TextStyle.paragraph, max_length=1500)
    acao = discord.ui.TextInput(label="Ação tomada / resultado", style=discord.TextStyle.paragraph, required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await _ps_cog(interaction).registrar_ocorrencia(interaction, self)


class BOModal(_PSModal, title="Boletim de Ocorrência"):
    tipo = discord.ui.TextInput(label="O que aconteceu?", placeholder="Ex: Furto, Agressão, Perda de documento", max_length=60)
    local = discord.ui.TextInput(label="Local do fato", max_length=100)
    quando = discord.ui.TextInput(label="Quando aconteceu?", placeholder="Ex: Hoje, por volta das 20h", max_length=60)
    descricao = discord.ui.TextInput(label="Relato", style=discord.TextStyle.paragraph, max_length=1500)
    envolvidos = discord.ui.TextInput(label="Suspeitos / testemunhas", style=discord.TextStyle.paragraph, required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await _ps_cog(interaction).registrar_bo(interaction, self)


class AcionamentoModal(_PSModal, title="Novo acionamento"):
    local = discord.ui.TextInput(label="Local", max_length=100)
    prioridade = discord.ui.TextInput(label="Prioridade", placeholder="Baixa, Média ou Alta", max_length=10, default="Média")
    descricao = discord.ui.TextInput(label="Situação", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await _ps_cog(interaction).registrar_acionamento(interaction, self)


class CandidaturaModal(_PSModal, title="Candidatura à Polícia Civil"):
    nome_rp = discord.ui.TextInput(label="Nome do personagem", max_length=60)
    idade = discord.ui.TextInput(label="Sua idade (real)", max_length=3)
    experiencia = discord.ui.TextInput(label="Experiência em RP", style=discord.TextStyle.paragraph, max_length=700)
    motivo = discord.ui.TextInput(label="Por que quer entrar?", style=discord.TextStyle.paragraph, max_length=700)
    disponibilidade = discord.ui.TextInput(label="Disponibilidade (dias/horários)", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await _ps_cog(interaction).candidatar(interaction, self)


class ReprovarModal(_PSModal, title="Reprovar candidato"):
    motivo = discord.ui.TextInput(label="Motivo (será enviado ao candidato)", style=discord.TextStyle.paragraph,
                                  required=False, max_length=500)

    def __init__(self, msg_id: int):
        super().__init__()
        self.msg_id = msg_id

    async def on_submit(self, interaction: discord.Interaction):
        await _ps_cog(interaction).reprovar_candidato(interaction, self.msg_id, self.motivo.value)


# ── views persistentes (custom_id fixo: continuam funcionando após reiniciar) ──
class PontoView(_PSView):
    @discord.ui.button(label="Entrar em serviço", emoji="🟢", style=discord.ButtonStyle.success, custom_id="ps_ponto_entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).ponto_entrar(interaction)

    @discord.ui.button(label="Sair de serviço", emoji="🔴", style=discord.ButtonStyle.danger, custom_id="ps_ponto_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).ponto_sair(interaction)

    @discord.ui.button(label="Minhas horas", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="ps_ponto_horas")
    async def horas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).ponto_horas(interaction)


class OcorrenciaView(_PSView):
    @discord.ui.button(label="Registrar ocorrência", emoji="📝", style=discord.ButtonStyle.primary, custom_id="ps_oc_novo")
    async def novo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _ps_cog(interaction)._tem(interaction.user, _PC_POL):
            await interaction.response.send_message("❌ Apenas policiais podem registrar ocorrências.", ephemeral=True)
            return
        await interaction.response.send_modal(OcorrenciaModal())


class BOView(_PSView):
    @discord.ui.button(label="Registrar boletim de ocorrência", emoji="📄", style=discord.ButtonStyle.primary, custom_id="ps_bo_novo")
    async def novo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BOModal())


class BOStatusView(_PSView):
    @discord.ui.button(label="Assumir", emoji="👀", style=discord.ButtonStyle.primary, custom_id="ps_bo_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).bo_acao(interaction, "assumir")

    @discord.ui.button(label="Concluir", emoji="✅", style=discord.ButtonStyle.success, custom_id="ps_bo_concluir")
    async def concluir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).bo_acao(interaction, "concluir")

    @discord.ui.button(label="Arquivar", emoji="🗄️", style=discord.ButtonStyle.secondary, custom_id="ps_bo_arquivar")
    async def arquivar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).bo_acao(interaction, "arquivar")


class AcionamentoPainelView(_PSView):
    @discord.ui.button(label="Novo acionamento", emoji="🚨", style=discord.ButtonStyle.danger, custom_id="ps_ac_novo")
    async def novo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _ps_cog(interaction)._tem(interaction.user, _PC_POL + ["core", "dep_op"]):
            await interaction.response.send_message("❌ Apenas policiais podem abrir acionamentos.", ephemeral=True)
            return
        await interaction.response.send_modal(AcionamentoModal())


class AcionamentoChamadoView(_PSView):
    @discord.ui.button(label="Atender", emoji="🚓", style=discord.ButtonStyle.primary, custom_id="ps_ac_atender")
    async def atender(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).ac_acao(interaction, "atender")

    @discord.ui.button(label="Encerrar", emoji="✅", style=discord.ButtonStyle.success, custom_id="ps_ac_encerrar")
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).ac_acao(interaction, "encerrar")


class _TicketSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            custom_id="ps_tk_tipo",
            placeholder="Escolha o motivo do atendimento...",
            options=[discord.SelectOption(label=l, value=v, emoji=e, description=d)
                     for v, (l, e, d) in _PS_TICKET_TIPOS.items()],
        )

    async def callback(self, interaction: discord.Interaction):
        await _ps_cog(interaction).abrir_ticket(interaction, self.values[0])


class TicketPainelView(_PSView):
    def __init__(self):
        super().__init__()
        self.add_item(_TicketSelect())


class TicketControlView(_PSView):
    @discord.ui.button(label="Assumir atendimento", emoji="🙋", style=discord.ButtonStyle.primary, custom_id="ps_tk_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).assumir_ticket(interaction)

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ps_tk_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).fechar_ticket(interaction)


class RecrutamentoView(_PSView):
    @discord.ui.button(label="Candidatar-se", emoji="📝", style=discord.ButtonStyle.success, custom_id="ps_rc_novo")
    async def novo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CandidaturaModal())


class RecrutamentoDecisaoView(_PSView):
    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success, custom_id="ps_rc_aprovar")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _ps_cog(interaction).aprovar_candidato(interaction)

    @discord.ui.button(label="Reprovar", emoji="❌", style=discord.ButtonStyle.danger, custom_id="ps_rc_reprovar")
    async def reprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = _ps_cog(interaction)
        if not cog._eh_recrutador(interaction.user):
            await interaction.response.send_message("❌ Apenas a equipe de recrutamento pode decidir.", ephemeral=True)
            return
        await interaction.response.send_modal(ReprovarModal(interaction.message.id))


# ── a cog ─────────────────────────────────────────────────────────────────
class PoliciaSistema(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        d = ler("policia_sistema")
        self.dados = d if isinstance(d, dict) else {}
        self.dados.setdefault("guilds", {})
        self._loop_ponto.start()
        self._loop_paineis.start()

    async def cog_load(self):
        for v in (PontoView(), OcorrenciaView(), BOView(), BOStatusView(), AcionamentoPainelView(),
                  AcionamentoChamadoView(), TicketPainelView(), TicketControlView(),
                  RecrutamentoView(), RecrutamentoDecisaoView()):
            self.bot.add_view(v)

    def cog_unload(self):
        self._loop_ponto.cancel()
        self._loop_paineis.cancel()

    # ── dados / utilidades ──
    def _salvar(self) -> None:
        try:
            salvar("policia_sistema", self.dados)
        except Exception as e:
            _log_erro("policia_sistema/salvar", e)

    def _g(self, guild: discord.Guild) -> dict:
        d = self.dados["guilds"].setdefault(str(guild.id), {})
        for k in ("canais", "paineis", "cont", "ponto", "tickets", "bo", "cand", "ac", "cooldown"):
            d.setdefault(k, {})
        return d

    def _proximo(self, guild: discord.Guild, nome: str) -> int:
        c = self._g(guild)["cont"]
        c[nome] = c.get(nome, 0) + 1
        self._salvar()
        return c[nome]

    def _role(self, guild: discord.Guild, key: str):
        return _pc_achar(guild.roles, _PS_NOMES[key])

    def _tem(self, member, keys) -> bool:
        roles = getattr(member, "roles", None)
        if not roles:
            return False
        meus = {r.id for r in roles}
        guild = member.guild
        return any((r := self._role(guild, k)) is not None and r.id in meus for k in keys)

    def _eh_comando(self, member) -> bool:
        if member.id == member.guild.owner_id or member.guild_permissions.administrator:
            return True
        return self._tem(member, _PC_AUTO)

    def _eh_recrutador(self, member) -> bool:
        return self._eh_comando(member) or self._tem(member, ["recrutador", "avaliador"] + _PC_TOP)

    def _canal(self, guild: discord.Guild, key: str):
        cid = self.dados["guilds"].get(str(guild.id), {}).get("canais", {}).get(key)
        ch = guild.get_channel(cid) if cid else None
        if ch is None:
            for k, _c, nome, _v, _w in _PS_CANAIS:
                if k == key:
                    ch = _pc_achar(guild.text_channels, nome)
                    break
        return ch

    async def _enviar(self, guild: discord.Guild, key: str, **kw):
        ch = self._canal(guild, key)
        if ch is None:
            return None
        try:
            return await ch.send(**kw)
        except discord.HTTPException as e:
            print(f"[SETAP] ⚠️ Não consegui enviar em {key}: {e}")
            return None

    async def _log(self, guild: discord.Guild, key: str, embed: discord.Embed):
        await self._enviar(guild, key, embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def _publicar_painel(self, guild, key, embed, view=None, criar: bool = True) -> bool:
        ch = self._canal(guild, key)
        if ch is None:
            return False
        g = self._g(guild)
        mid = g["paineis"].get(key)
        if mid:
            try:
                msg = await ch.fetch_message(mid)
                await msg.edit(embed=embed, view=view)
                return True
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return False
        if not criar:
            return False
        try:
            msg = await ch.send(embed=embed, view=view)
        except discord.HTTPException:
            return False
        g["paineis"][key] = msg.id
        self._salvar()
        return True

    @staticmethod
    def _embed(titulo: str, desc: str = "", cor: int = _PS_COR) -> discord.Embed:
        e = discord.Embed(title=titulo, description=desc, color=cor)
        e.set_footer(text="Polícia Civil • Sistema automático")
        return e

    # ══════════════════ !setap ══════════════════
    @commands.command(name="setap")
    @commands.guild_only()
    async def setap(self, ctx: commands.Context):
        guild = ctx.guild
        if not self._eh_comando(ctx.author):
            await ctx.send("❌ Apenas o proprietário, administradores ou o comando podem usar este comando.", delete_after=8)
            return
        if not guild.me.guild_permissions.manage_channels:
            await ctx.send("❌ Eu preciso da permissão **Gerenciar Canais** (ou Administrador).")
            return
        mapa = {k: r for k, n, *_ in _PC_CARGOS if (r := _pc_achar(guild.roles, n)) is not None}
        faltam = [k for k in ("chefe", "admin", "cidadao", "servico", "fora", "agente", "bots") if k not in mapa]
        if faltam:
            await ctx.send("❌ Faltam cargos da Polícia Civil no servidor. Rode primeiro `!pconlycargos` e depois `!setap`.")
            return
        lock = _PC_LOCKS.setdefault(guild.id, asyncio.Lock())
        if lock.locked():
            await ctx.send("⏳ Já existe uma operação em andamento.")
            return

        async with lock:
            aviso = await ctx.send("⚙️ Configurando canais e painéis... pode levar alguns minutos.")
            g = self._g(guild)
            falhas: list[str] = []
            criados = atualizados = 0

            # categorias novas (ponto, atendimentos, logs)
            cats: dict[str, discord.CategoryChannel] = {}
            for nome, view in _PS_CATEGORIAS_NOVAS.items():
                cat = _pc_achar(guild.categories, nome)
                try:
                    ow = Whitelist._pc_overwrites(guild, mapa, view, [], False)
                    if cat is None:
                        cat = await guild.create_category(name=nome, overwrites=ow, reason="!setap")
                    else:
                        await cat.edit(overwrites=ow, reason="!setap")
                    cats[nome] = cat
                except discord.HTTPException as e:
                    falhas.append(f"Categoria {nome}: {getattr(e, 'text', e)}")
                await asyncio.sleep(0.5)

            # canais funcionais
            for key, cat_nome, nome, view, write in _PS_CANAIS:
                try:
                    cat = cats.get(cat_nome) or _pc_achar(guild.categories, cat_nome)
                    if cat is None:
                        cat = await guild.create_category(
                            name=cat_nome, overwrites=Whitelist._pc_overwrites(guild, mapa, view, [], False), reason="!setap")
                        cats[cat_nome] = cat
                    ow = Whitelist._pc_overwrites(guild, mapa, view, write, False)
                    ch = _pc_achar(guild.text_channels, nome)
                    if ch is None:
                        ch = await guild.create_text_channel(name=nome, category=cat, overwrites=ow, reason="!setap")
                        criados += 1
                    else:
                        await ch.edit(overwrites=ow, reason="!setap — permissões")
                        atualizados += 1
                    g["canais"][key] = ch.id
                except discord.HTTPException as e:
                    falhas.append(f"Canal {nome}: {getattr(e, 'text', e)}")
                await asyncio.sleep(0.5)
            self._salvar()

            # painéis
            paineis = [
                ("ponto", self._emb_ponto(), PontoView()),
                ("oc_painel", self._emb_ocorrencia(), OcorrenciaView()),
                ("bo_painel", self._emb_bo(), BOView()),
                ("tk_painel", self._emb_ticket(), TicketPainelView()),
                ("rec_painel", self._emb_recrutamento(), RecrutamentoView()),
                ("regulamento", self._emb_regulamento(), None),
                ("como_ingressar", self._emb_ingressar(guild), None),
                ("comandos", self._emb_comandos(), None),
                ("hierarquia", self._emb_hierarquia(guild), None),
                ("departamentos", self._emb_departamentos(guild), None),
                ("ranking", self._emb_ranking(guild), None),
            ]
            publicados = 0
            for key, emb, view in paineis:
                if await self._publicar_painel(guild, key, emb, view):
                    publicados += 1
                else:
                    falhas.append(f"Painel '{key}' não publicado (canal ausente ou sem permissão)")
                await asyncio.sleep(0.5)
            await self._repostar_painel_acionamento(guild)
            publicados += 1

            embed = self._embed("✅ Sistema da Polícia Civil configurado")
            embed.color = 0x57F287 if not falhas else 0xFEE75C
            embed.add_field(name="📂 Canais", value=f"Criados: {criados}\nAtualizados: {atualizados}", inline=True)
            embed.add_field(name="📌 Painéis", value=f"{publicados} publicados/atualizados", inline=True)
            embed.add_field(name="⚙️ Funções ativas", value=(
                "🕒 **Ponto** — entrar/sair de serviço, horas, ranking e encerramento automático (12h)\n"
                "📋 **Ocorrências** — registro policial com protocolo\n"
                "📄 **Boletim de Ocorrência** — cidadão registra, polícia assume/conclui\n"
                "🚨 **Acionamentos** — chamado com ping em quem está em serviço\n"
                "🎫 **Atendimento ao cidadão** — tickets privados com transcrição\n"
                "📝 **Recrutamento** — candidatura, aprovação/reprovação e cargos\n"
                "👋 **Boas-vindas e saídas** — + 🛠️ logs de mensagens, voz, cargos e moderação\n"
                "🏅 **Hierarquia e departamentos** ao vivo · 📈 `!promover` / `!rebaixar` · 💡 sugestões com votação"
            ), inline=False)
            if falhas:
                texto = "\n".join(f"• {f}" for f in falhas[:8])
                embed.add_field(name=f"⚠️ Falhas ({len(falhas)})", value=texto[:1024], inline=False)
            try:
                await aviso.edit(content=None, embed=embed)
            except discord.HTTPException:
                await ctx.send(embed=embed)

    # ══════════════════ embeds dos painéis ══════════════════
    def _emb_ponto(self) -> discord.Embed:
        return self._embed("🕒 Bater Ponto", (
            "Registre sua entrada e saída de serviço.\n\n"
            "🟢 **Entrar em serviço** — recebe o cargo *Em Serviço*\n"
            "🔴 **Sair de serviço** — registra o tempo e volta para *Fora de Serviço*\n"
            "📊 **Minhas horas** — total acumulado\n\n"
            "⚠️ Turnos esquecidos abertos por mais de **12h** são encerrados automaticamente."
        ), 0x2E7D32)

    def _emb_ocorrencia(self) -> discord.Embed:
        return self._embed("📋 Registro de Ocorrências", (
            "Policial, registre aqui toda ocorrência atendida.\n"
            "Clique no botão, preencha o formulário e o registro vai para "
            "o arquivo oficial com um **protocolo** próprio."
        ))

    def _emb_bo(self) -> discord.Embed:
        return self._embed("📄 Boletim de Ocorrência", (
            "Foi vítima ou testemunha de um crime? Registre seu boletim.\n\n"
            "1️⃣ Clique no botão abaixo\n2️⃣ Preencha o relato com o máximo de detalhes\n"
            "3️⃣ Você recebe o **número do protocolo** e a polícia assume o caso\n\n"
            "Para falar diretamente com um policial use o canal de atendimento ao cidadão."
        ), 0xFEE75C)

    def _emb_ticket(self) -> discord.Embed:
        return self._embed("👥 Atendimento ao Cidadão", (
            "Precisa falar com a Polícia Civil? Abra um atendimento **privado**.\n\n"
            + "\n".join(f"{e} **{l}** — {d}" for l, e, d in _PS_TICKET_TIPOS.values())
            + "\n\nEscolha o motivo no menu abaixo. Só você e os policiais verão o atendimento."
        ), 0x00A6A6)

    def _emb_recrutamento(self) -> discord.Embed:
        return self._embed("📝 Inscrições — Polícia Civil", (
            "Quer vestir a farda? Envie sua candidatura!\n\n"
            "• Clique em **Candidatar-se** e preencha o formulário\n"
            "• A equipe de recrutamento avalia e responde por aqui e na sua DM\n"
            "• Aprovados entram na **Academia de Polícia**\n\n"
            "Mantenha suas mensagens privadas abertas para receber o resultado."
        ), 0x00897B)

    def _emb_regulamento(self) -> discord.Embed:
        return self._embed("📜 Regulamento", (
            "**1.** Respeito acima de tudo: sem ofensas, preconceito ou assédio.\n"
            "**2.** Mantenha o roleplay: sem *metagaming* ou *powergaming*.\n"
            "**3.** Respeite a hierarquia e cumpra as ordens do comando.\n"
            "**4.** Bata ponto ao entrar e sair de serviço; abuso gera advertência.\n"
            "**5.** Sigilo: casos e informações confidenciais não saem dos canais autorizados.\n"
            "**6.** Use cada canal para o seu fim; sem spam ou divulgação.\n"
            "**7.** Condutas suspeitas vão para a Corregedoria; suas decisões são finais.\n"
            "**8.** Desconhecer as regras não isenta de punição.\n\n"
            "Ao permanecer no servidor você concorda com este regulamento."
        ), 0xED4245)

    def _emb_ingressar(self, guild: discord.Guild) -> discord.Embed:
        insc = self._canal(guild, "rec_painel")
        reg = self._canal(guild, "regulamento")
        return self._embed("📋 Como ingressar na Polícia Civil", (
            f"**1.** Leia o regulamento {reg.mention if reg else ''}\n"
            f"**2.** Envie sua candidatura em {insc.mention if insc else 'inscrições'}\n"
            "**3.** Aguarde a avaliação da equipe de recrutamento\n"
            "**4.** Aprovado, você ingressa na **Academia de Polícia** como aluno\n"
            "**5.** Conclua o treinamento e comece a carreira como **Agente de Polícia**\n\n"
            "Dúvidas? Abra um atendimento ou pergunte em **dúvidas**."
        ), 0x00897B)

    def _emb_comandos(self) -> discord.Embed:
        return self._embed("🤖 Comandos e recursos do bot", (
            "**Painéis (botões)**\n"
            "🕒 Bater ponto · 📋 Ocorrências · 📄 Boletim · 🚨 Acionamento · 🎫 Atendimento · 📝 Inscrição\n\n"
            "**Comandos**\n"
            "`!horas [@policial]` — horas de serviço\n"
            "`!promover @policial [motivo]` — promove um posto (comando)\n"
            "`!rebaixar @policial [motivo]` — rebaixa um posto (comando)\n"
            "`!setap` — recria/atualiza canais e painéis (comando)"
        ))

    def _emb_hierarquia(self, guild: discord.Guild) -> discord.Embed:
        e = self._embed("🏅 Hierarquia Policial", "Quadro atualizado automaticamente.")
        for key in _PS_HIERARQUIA:
            role = self._role(guild, key)
            if role is None:
                continue
            membros = [m.mention for m in role.members if not m.bot]
            if not membros:
                valor = "*Vago*"
            else:
                valor = " ".join(membros[:15]) + (f" +{len(membros) - 15}" if len(membros) > 15 else "")
            e.add_field(name=role.name, value=valor[:1024], inline=False)
        return e

    def _emb_departamentos(self, guild: discord.Guild) -> discord.Embed:
        e = self._embed("🏢 Departamentos e Divisões", "Conheça as áreas da corporação.")
        for key, desc in _PS_DEPARTAMENTOS:
            role = self._role(guild, key)
            if role is None:
                continue
            e.add_field(name=role.name, value=f"{desc}\n👥 **{len([m for m in role.members if not m.bot])}** membro(s)", inline=False)
        return e

    def _emb_ranking(self, guild: discord.Guild) -> discord.Embed:
        ponto = self._g(guild)["ponto"]
        agora = time.time()
        itens = []
        for uid, reg in ponto.items():
            total = reg.get("total", 0) + (agora - reg["inicio"] if reg.get("inicio") else 0)
            if total > 0:
                itens.append((total, uid, bool(reg.get("inicio"))))
        itens.sort(reverse=True)
        medalhas = ["🥇", "🥈", "🥉"]
        linhas = [
            f"{medalhas[i] if i < 3 else f'`{i + 1}º`'} <@{uid}> — **{_ps_dur(total)}**" + (" 🟢" if ativo else "")
            for i, (total, uid, ativo) in enumerate(itens[:10])
        ]
        em_servico = sum(1 for r in ponto.values() if r.get("inicio"))
        e = self._embed("🏆 Ranking de Horas", "\n".join(linhas) or "Ninguém bateu ponto ainda.", 0xFF8F00)
        e.add_field(name="🟢 Em serviço agora", value=str(em_servico), inline=True)
        e.add_field(name="🔄 Atualizado", value=f"<t:{int(agora)}:R>", inline=True)
        return e

    def _emb_acionamento(self) -> discord.Embed:
        return self._embed("🚨 Central de Acionamentos", (
            "Precisa de apoio ou há uma ocorrência em andamento?\n"
            "Clique em **Novo acionamento**: quem está **em serviço** será chamado."
        ), 0xED4245)

    async def _repostar_painel_acionamento(self, guild: discord.Guild) -> None:
        ch = self._canal(guild, "acionamentos")
        if ch is None:
            return
        g = self._g(guild)
        mid = g["paineis"].get("acionamentos")
        if mid:
            try:
                await (await ch.fetch_message(mid)).delete()
            except discord.HTTPException:
                pass
        try:
            msg = await ch.send(embed=self._emb_acionamento(), view=AcionamentoPainelView())
            g["paineis"]["acionamentos"] = msg.id
            self._salvar()
        except discord.HTTPException:
            pass

    # ══════════════════ PONTO ══════════════════
    async def _trocar_servico(self, guild, member, entrando: bool) -> None:
        on, off = self._role(guild, "servico"), self._role(guild, "fora")
        try:
            add, rem = (on, off) if entrando else (off, on)
            if rem is not None and rem in member.roles:
                await member.remove_roles(rem, reason="Ponto")
            if add is not None and add not in member.roles:
                await member.add_roles(add, reason="Ponto")
        except discord.HTTPException:
            pass

    async def ponto_entrar(self, interaction: discord.Interaction):
        guild, m = interaction.guild, interaction.user
        if not self._tem(m, _PC_POL):
            await interaction.response.send_message("❌ Apenas policiais podem bater ponto.", ephemeral=True)
            return
        reg = self._g(guild)["ponto"].setdefault(str(m.id), {"inicio": None, "total": 0, "sessoes": 0})
        if reg.get("inicio"):
            await interaction.response.send_message(f"⚠️ Você já está em serviço desde <t:{int(reg['inicio'])}:R>.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        reg["inicio"] = time.time()
        self._salvar()
        await self._trocar_servico(guild, m, True)
        e = discord.Embed(title="🟢 Entrada em serviço", description=m.mention, color=0x2E7D32, timestamp=discord.utils.utcnow())
        e.set_thumbnail(url=m.display_avatar.url)
        await self._log(guild, "ponto_log", e)
        await interaction.followup.send("🟢 Você entrou em serviço. Bom trabalho!", ephemeral=True)

    async def _fechar_sessao(self, guild, uid: int, member, auto: bool = False, saiu: bool = False):
        reg = self._g(guild)["ponto"].get(str(uid))
        if not reg or not reg.get("inicio"):
            return None
        dur = time.time() - reg["inicio"]
        if auto:
            dur = min(dur, _PS_LIMITE_PONTO)
        reg["total"] = reg.get("total", 0) + dur
        reg["sessoes"] = reg.get("sessoes", 0) + 1
        reg["inicio"] = None
        self._salvar()
        if member is not None and not saiu:
            await self._trocar_servico(guild, member, False)
        e = discord.Embed(title="🔴 Saída de serviço", description=f"<@{uid}>", color=0xC62828, timestamp=discord.utils.utcnow())
        e.add_field(name="⏱️ Duração", value=_ps_dur(dur), inline=True)
        e.add_field(name="📊 Total acumulado", value=_ps_dur(reg["total"]), inline=True)
        if auto:
            e.set_footer(text="Encerrado automaticamente (turno aberto por mais de 12h)")
        elif saiu:
            e.set_footer(text="Encerrado: saiu do servidor")
        await self._log(guild, "ponto_log", e)
        await self._publicar_painel(guild, "ranking", self._emb_ranking(guild), None, criar=False)
        return dur, reg["total"]

    async def ponto_sair(self, interaction: discord.Interaction):
        guild, m = interaction.guild, interaction.user
        if not self._tem(m, _PC_POL):
            await interaction.response.send_message("❌ Apenas policiais podem bater ponto.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        r = await self._fechar_sessao(guild, m.id, m)
        if r is None:
            await interaction.followup.send("⚠️ Você não está em serviço.", ephemeral=True)
            return
        dur, total = r
        await interaction.followup.send(f"🔴 Saída registrada. Turno: **{_ps_dur(dur)}** · Total: **{_ps_dur(total)}**", ephemeral=True)

    def _horas_txt(self, guild, uid: int) -> str:
        reg = self._g(guild)["ponto"].get(str(uid))
        if not reg:
            return "Nenhum registro de ponto ainda."
        atual = f"\n🟢 Turno atual: **{_ps_dur(time.time() - reg['inicio'])}**" if reg.get("inicio") else ""
        return f"⏱️ Total: **{_ps_dur(reg.get('total', 0))}** em **{reg.get('sessoes', 0)}** turno(s){atual}"

    async def ponto_horas(self, interaction: discord.Interaction):
        await interaction.response.send_message(self._horas_txt(interaction.guild, interaction.user.id), ephemeral=True)

    @commands.command(name="horas")
    @commands.guild_only()
    async def horas(self, ctx: commands.Context, membro: discord.Member = None):
        membro = membro or ctx.author
        await ctx.send(f"📊 **{membro.display_name}**\n{self._horas_txt(ctx.guild, membro.id)}")

    @tasks.loop(minutes=10)
    async def _loop_ponto(self):
        agora = time.time()
        for gid, g in list(self.dados["guilds"].items()):
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue
            for uid, reg in list(g.get("ponto", {}).items()):
                if reg.get("inicio") and agora - reg["inicio"] >= _PS_LIMITE_PONTO:
                    try:
                        await self._fechar_sessao(guild, int(uid), guild.get_member(int(uid)), auto=True)
                    except Exception as e:
                        _log_erro("loop_ponto", e)

    @_loop_ponto.before_loop
    async def _antes_loop_ponto(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def _loop_paineis(self):
        for gid in list(self.dados["guilds"].keys()):
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue
            try:
                for key, emb in (("hierarquia", self._emb_hierarquia(guild)),
                                 ("departamentos", self._emb_departamentos(guild)),
                                 ("ranking", self._emb_ranking(guild))):
                    await self._publicar_painel(guild, key, emb, None, criar=False)
                    await asyncio.sleep(1)
            except Exception as e:
                _log_erro("loop_paineis", e)

    @_loop_paineis.before_loop
    async def _antes_loop_paineis(self):
        await self.bot.wait_until_ready()

    # ══════════════════ OCORRÊNCIAS / BO / ACIONAMENTOS ══════════════════
    async def registrar_ocorrencia(self, interaction: discord.Interaction, m: OcorrenciaModal):
        guild, u = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        n = self._proximo(guild, "oc")
        e = discord.Embed(title=f"📋 Ocorrência #{n:04d} — {_ps_txt(m.tipo.value, 80)}", color=_PS_COR, timestamp=discord.utils.utcnow())
        e.set_author(name=str(u), icon_url=u.display_avatar.url)
        e.add_field(name="📍 Local", value=_ps_txt(m.local.value), inline=True)
        e.add_field(name="👮 Responsável", value=u.mention, inline=True)
        e.add_field(name="📝 Descrição", value=_ps_txt(m.descricao.value), inline=False)
        e.add_field(name="👥 Envolvidos", value=_ps_txt(m.envolvidos.value), inline=False)
        e.add_field(name="✅ Ação / resultado", value=_ps_txt(m.acao.value), inline=False)
        msg = await self._enviar(guild, "oc_log", embed=e, allowed_mentions=discord.AllowedMentions.none())
        if msg is None:
            await interaction.followup.send("⚠️ Canal de ocorrências não encontrado. Peça ao comando para rodar `!setap`.", ephemeral=True)
            return
        await interaction.followup.send(f"✅ Ocorrência **#{n:04d}** registrada: {msg.jump_url}", ephemeral=True)

    async def registrar_bo(self, interaction: discord.Interaction, m: BOModal):
        guild, u = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        g = self._g(guild)
        ult = g["cooldown"].get(f"bo:{u.id}", 0)
        if time.time() - ult < 120:
            await interaction.followup.send("⏳ Aguarde um pouco antes de registrar outro boletim.", ephemeral=True)
            return
        n = self._proximo(guild, "bo")
        e = discord.Embed(title=f"📄 Boletim #{n:04d} — {_ps_txt(m.tipo.value, 80)}", color=0xFEE75C, timestamp=discord.utils.utcnow())
        e.set_author(name=str(u), icon_url=u.display_avatar.url)
        e.add_field(name="📍 Local", value=_ps_txt(m.local.value), inline=True)
        e.add_field(name="🕒 Quando", value=_ps_txt(m.quando.value), inline=True)
        e.add_field(name="👤 Declarante", value=u.mention, inline=True)
        e.add_field(name="📝 Relato", value=_ps_txt(m.descricao.value), inline=False)
        e.add_field(name="👥 Suspeitos / testemunhas", value=_ps_txt(m.envolvidos.value), inline=False)
        e.add_field(name="📌 Status", value="🟡 Aberto", inline=True)
        e.add_field(name="👮 Responsável", value="—", inline=True)
        e.set_footer(text=f"ID do declarante: {u.id}")
        msg = await self._enviar(guild, "bo_recebidos", embed=e, view=BOStatusView(), allowed_mentions=discord.AllowedMentions.none())
        if msg is None:
            await interaction.followup.send("⚠️ Não consegui registrar agora. Avise a staff.", ephemeral=True)
            return
        g["bo"][str(msg.id)] = {"n": n, "user": u.id, "status": "aberto", "resp": None}
        g["cooldown"][f"bo:{u.id}"] = time.time()
        self._salvar()
        await interaction.followup.send(f"✅ Boletim registrado! Seu protocolo é **#{n:04d}**. Um policial vai assumir o caso.", ephemeral=True)

    async def bo_acao(self, interaction: discord.Interaction, acao: str):
        guild, m = interaction.guild, interaction.user
        if not (self._tem(m, _PC_POL) or self._eh_comando(m)):
            await interaction.response.send_message("❌ Apenas policiais podem mexer nos boletins.", ephemeral=True)
            return
        reg = self._g(guild)["bo"].get(str(interaction.message.id))
        if not reg:
            await interaction.response.send_message("⚠️ Não achei os dados desse boletim.", ephemeral=True)
            return
        if reg["status"] in ("concluido", "arquivado"):
            await interaction.response.send_message("⚠️ Esse boletim já foi encerrado.", ephemeral=True)
            return
        resp = reg.get("resp")
        if resp and resp != m.id and not self._eh_comando(m):
            await interaction.response.send_message(f"🔒 Esse boletim está com <@{resp}>.", ephemeral=True)
            return
        e = interaction.message.embeds[0].copy()
        view = BOStatusView()
        if acao == "assumir":
            reg["status"], reg["resp"] = "andamento", m.id
            _ps_set_field(e, "📌 Status", "🔵 Em andamento")
            _ps_set_field(e, "👮 Responsável", m.mention)
            e.color = 0x5865F2
        elif acao == "concluir":
            reg["status"] = "concluido"
            _ps_set_field(e, "📌 Status", "🟢 Concluído")
            _ps_set_field(e, "👮 Responsável", m.mention)
            e.color, view = 0x57F287, None
        else:
            reg["status"] = "arquivado"
            _ps_set_field(e, "📌 Status", "⚫ Arquivado")
            e.color, view = 0x99AAB5, None
        self._salvar()
        await interaction.response.edit_message(embed=e, view=view)
        if acao == "concluir":
            u = guild.get_member(reg["user"])
            if u:
                try:
                    await u.send(f"✅ Seu boletim **#{reg['n']:04d}** na Polícia Civil foi **concluído** por {m.display_name}.")
                except discord.HTTPException:
                    pass

    async def registrar_acionamento(self, interaction: discord.Interaction, m: AcionamentoModal):
        guild, u = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        n = self._proximo(guild, "ac")
        p = m.prioridade.value.strip().lower()
        cor, nivel = (0xED4245, "🔴 Alta") if p.startswith("alt") else (0xFF8F00, "🟠 Média") if p.startswith(("méd", "med")) else (0x57F287, "🟢 Baixa")
        e = discord.Embed(title=f"🚨 Acionamento #{n:04d}", color=cor, timestamp=discord.utils.utcnow())
        e.add_field(name="📍 Local", value=_ps_txt(m.local.value), inline=True)
        e.add_field(name="⚡ Prioridade", value=nivel, inline=True)
        e.add_field(name="📝 Situação", value=_ps_txt(m.descricao.value), inline=False)
        e.add_field(name="📌 Status", value="🟡 Aguardando equipe", inline=True)
        e.add_field(name="🚓 Equipe", value="—", inline=True)
        e.set_footer(text=f"Aberto por {u}")
        role = self._role(guild, "servico")
        msg = await self._enviar(
            guild, "acionamentos", content=role.mention if role else None, embed=e, view=AcionamentoChamadoView(),
            allowed_mentions=discord.AllowedMentions(roles=[role]) if role else discord.AllowedMentions.none(),
        )
        if msg is None:
            await interaction.followup.send("⚠️ Canal de acionamentos não encontrado. Rode `!setap`.", ephemeral=True)
            return
        self._g(guild)["ac"][str(msg.id)] = {"n": n, "autor": u.id, "equipe": [], "status": "aberto"}
        self._salvar()
        await self._repostar_painel_acionamento(guild)
        await interaction.followup.send(f"🚨 Acionamento **#{n:04d}** enviado!", ephemeral=True)

    async def ac_acao(self, interaction: discord.Interaction, acao: str):
        guild, m = interaction.guild, interaction.user
        if not (self._tem(m, _PC_POL + ["core", "dep_op"]) or self._eh_comando(m)):
            await interaction.response.send_message("❌ Apenas policiais podem atender acionamentos.", ephemeral=True)
            return
        reg = self._g(guild)["ac"].get(str(interaction.message.id))
        if not reg:
            await interaction.response.send_message("⚠️ Não achei os dados desse acionamento.", ephemeral=True)
            return
        if reg["status"] == "encerrado":
            await interaction.response.send_message("⚠️ Esse acionamento já foi encerrado.", ephemeral=True)
            return
        e = interaction.message.embeds[0].copy()
        view = AcionamentoChamadoView()
        if acao == "atender":
            if m.id in reg["equipe"]:
                await interaction.response.send_message("⚠️ Você já está nesse acionamento.", ephemeral=True)
                return
            reg["equipe"].append(m.id)
            reg["status"] = "andamento"
            _ps_set_field(e, "📌 Status", "🔵 Em atendimento")
            _ps_set_field(e, "🚓 Equipe", " ".join(f"<@{i}>" for i in reg["equipe"]))
        else:
            if reg["equipe"] and m.id not in reg["equipe"] and not self._eh_comando(m):
                await interaction.response.send_message("🔒 Só a equipe do acionamento (ou o comando) pode encerrar.", ephemeral=True)
                return
            reg["status"] = "encerrado"
            _ps_set_field(e, "📌 Status", f"✅ Encerrado por {m.mention}")
            e.color, view = 0x57F287, None
        self._salvar()
        await interaction.response.edit_message(embed=e, view=view)

    # ══════════════════ ATENDIMENTO AO CIDADÃO (tickets) ══════════════════
    async def abrir_ticket(self, interaction: discord.Interaction, tipo: str):
        guild, m = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        g = self._g(guild)
        for cid, t in list(g["tickets"].items()):
            ch = guild.get_channel(int(cid))
            if ch is None:
                g["tickets"].pop(cid, None)
            elif t["user"] == m.id:
                await interaction.followup.send(f"⚠️ Você já tem um atendimento aberto: {ch.mention}", ephemeral=True)
                return
        label, emoji, _d = _PS_TICKET_TIPOS.get(tipo, _PS_TICKET_TIPOS["outro"])
        cat = _pc_achar(guild.categories, _PS_CAT_TICKETS)
        po = discord.PermissionOverwrite
        ow = {
            guild.default_role: po(view_channel=False),
            m: po(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: po(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
        }
        for k in dict.fromkeys(_PS_STAFF_TICKET + ["admin"]):
            r = self._role(guild, k)
            if r is not None:
                ow[r] = po(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        n = self._proximo(guild, "tk")
        try:
            ch = await guild.create_text_channel(
                name=f"🎫・{_slug(label)}-{_slug(m.name)}"[:90], category=cat, overwrites=ow,
                topic=f"Atendimento #{n:04d} — {label} — {m} ({m.id})", reason=f"Atendimento aberto por {m}",
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"⚠️ Não consegui abrir o atendimento: {getattr(e, 'text', e)}", ephemeral=True)
            return
        g["tickets"][str(ch.id)] = {"n": n, "user": m.id, "tipo": label, "assumido": None, "aberto": time.time()}
        self._salvar()
        e = self._embed(f"{emoji} Atendimento #{n:04d} — {label}", (
            f"Olá, {m.mention}! Descreva sua situação com o máximo de detalhes.\n"
            "Um policial vai atender você em breve.\n\n"
            "🙋 **Assumir** — policial assume o atendimento\n🔒 **Fechar** — encerra e gera a transcrição"
        ), 0x00A6A6)
        plantao = self._role(guild, "plantao")
        await ch.send(
            content=f"{m.mention} {plantao.mention if plantao else ''}".strip(), embed=e, view=TicketControlView(),
            allowed_mentions=discord.AllowedMentions(users=[m], roles=[plantao] if plantao else []),
        )
        await interaction.followup.send(f"✅ Atendimento aberto: {ch.mention}", ephemeral=True)

    def _pode_ticket(self, member, reg: dict) -> bool:
        return member.id == reg["user"] or self._tem(member, _PS_STAFF_TICKET) or self._eh_comando(member)

    async def assumir_ticket(self, interaction: discord.Interaction):
        guild, m = interaction.guild, interaction.user
        reg = self._g(guild)["tickets"].get(str(interaction.channel.id))
        if not reg:
            await interaction.response.send_message("⚠️ Não achei os dados desse atendimento.", ephemeral=True)
            return
        if not (self._tem(m, _PS_STAFF_TICKET) or self._eh_comando(m)):
            await interaction.response.send_message("❌ Apenas policiais podem assumir atendimentos.", ephemeral=True)
            return
        if reg.get("assumido"):
            await interaction.response.send_message(f"⚠️ Já assumido por <@{reg['assumido']}>.", ephemeral=True)
            return
        reg["assumido"] = m.id
        self._salvar()
        await interaction.response.send_message(f"🙋 {m.mention} assumiu este atendimento.", allowed_mentions=discord.AllowedMentions.none())

    async def fechar_ticket(self, interaction: discord.Interaction):
        guild, m, ch = interaction.guild, interaction.user, interaction.channel
        g = self._g(guild)
        reg = g["tickets"].get(str(ch.id))
        if not reg:
            await interaction.response.send_message("⚠️ Não achei os dados desse atendimento.", ephemeral=True)
            return
        if not self._pode_ticket(m, reg):
            await interaction.response.send_message("❌ Você não pode fechar este atendimento.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Gerando transcrição e fechando o atendimento...")
        fuso = timezone(timedelta(hours=-3))
        linhas = []
        try:
            async for msg in ch.history(limit=2000, oldest_first=True):
                anexos = " ".join(a.url for a in msg.attachments)
                linhas.append(f"[{msg.created_at.astimezone(fuso):%d/%m/%Y %H:%M}] {msg.author}: {msg.clean_content} {anexos}".strip())
        except discord.HTTPException:
            pass
        nome_arq = f"atendimento-{reg['n']:04d}.txt"
        dados = "\n".join(linhas).encode("utf-8")
        e = discord.Embed(title=f"🗃️ Atendimento #{reg['n']:04d} encerrado", color=0x99AAB5, timestamp=discord.utils.utcnow())
        e.add_field(name="Tipo", value=reg["tipo"], inline=True)
        e.add_field(name="Cidadão", value=f"<@{reg['user']}>", inline=True)
        e.add_field(name="Responsável", value=f"<@{reg['assumido']}>" if reg.get("assumido") else "—", inline=True)
        e.add_field(name="Duração", value=_ps_dur(time.time() - reg["aberto"]), inline=True)
        e.add_field(name="Fechado por", value=m.mention, inline=True)
        await self._enviar(guild, "log_tk", embed=e, file=discord.File(io.BytesIO(dados), filename=nome_arq),
                           allowed_mentions=discord.AllowedMentions.none())
        u = guild.get_member(reg["user"])
        if u:
            try:
                await u.send(f"🔒 Seu atendimento **#{reg['n']:04d}** na Polícia Civil foi encerrado. Segue a transcrição:",
                             file=discord.File(io.BytesIO(dados), filename=nome_arq))
            except discord.HTTPException:
                pass
        g["tickets"].pop(str(ch.id), None)
        self._salvar()
        await asyncio.sleep(4)
        try:
            await ch.delete(reason=f"Atendimento encerrado por {m}")
        except discord.HTTPException:
            pass

    # ══════════════════ RECRUTAMENTO ══════════════════
    async def candidatar(self, interaction: discord.Interaction, m: CandidaturaModal):
        guild, u = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        if self._tem(u, _PC_POL + ["aluno"]):
            await interaction.followup.send("⚠️ Você já faz parte da corporação.", ephemeral=True)
            return
        g = self._g(guild)
        if any(c["user"] == u.id and c["status"] == "pendente" for c in g["cand"].values()):
            await interaction.followup.send("⚠️ Você já tem uma candidatura em análise. Aguarde o resultado.", ephemeral=True)
            return
        n = self._proximo(guild, "rc")
        e = discord.Embed(title=f"📝 Candidatura #{n:04d} — {_ps_txt(m.nome_rp.value, 60)}", color=0xFEE75C, timestamp=discord.utils.utcnow())
        e.set_author(name=str(u), icon_url=u.display_avatar.url)
        e.add_field(name="👤 Candidato", value=u.mention, inline=True)
        e.add_field(name="🎂 Idade", value=_ps_txt(m.idade.value, 10), inline=True)
        e.add_field(name="🕒 Disponibilidade", value=_ps_txt(m.disponibilidade.value, 100), inline=True)
        e.add_field(name="🎮 Experiência em RP", value=_ps_txt(m.experiencia.value), inline=False)
        e.add_field(name="💬 Motivo", value=_ps_txt(m.motivo.value), inline=False)
        e.add_field(name="📌 Status", value="🟡 Pendente", inline=False)
        e.set_footer(text=f"ID: {u.id}")
        rec = self._role(guild, "recrutador")
        msg = await self._enviar(
            guild, "rec_equipe", content=rec.mention if rec else None, embed=e, view=RecrutamentoDecisaoView(),
            allowed_mentions=discord.AllowedMentions(roles=[rec]) if rec else discord.AllowedMentions.none(),
        )
        if msg is None:
            await interaction.followup.send("⚠️ Não consegui enviar a candidatura agora. Avise a staff.", ephemeral=True)
            return
        g["cand"][str(msg.id)] = {"n": n, "user": u.id, "status": "pendente"}
        self._salvar()
        await interaction.followup.send(f"✅ Candidatura **#{n:04d}** enviada! O resultado sai aqui no servidor e na sua DM.", ephemeral=True)

    async def _finalizar_candidatura(self, guild, msg: discord.Message, reg: dict, aprovado: bool, autor, motivo: str = "") -> None:
        reg["status"] = "aprovado" if aprovado else "reprovado"
        self._salvar()
        e = msg.embeds[0].copy()
        _ps_set_field(e, "📌 Status", (f"✅ Aprovado por {autor.mention}" if aprovado else f"❌ Reprovado por {autor.mention}"), inline=False)
        e.color = 0x57F287 if aprovado else 0xED4245
        await msg.edit(embed=e, view=None)
        cand = guild.get_member(reg["user"])
        mencao = cand.mention if cand else f"<@{reg['user']}>"
        if aprovado:
            aluno = self._role(guild, "aluno")
            if cand and aluno:
                try:
                    await cand.add_roles(aluno, reason=f"Candidatura aprovada por {autor}")
                except discord.HTTPException:
                    pass
            r = self._embed(f"✅ Candidatura #{reg['n']:04d} aprovada", f"{mencao} foi **aprovado(a)**! Bem-vindo(a) à Academia de Polícia. 🎓", 0x57F287)
            await self._enviar(guild, "aprovados", embed=r, allowed_mentions=discord.AllowedMentions(users=True))
            dm = "🎉 Sua candidatura à Polícia Civil foi **aprovada**! Você agora é aluno da Academia de Polícia."
        else:
            r = self._embed(f"❌ Candidatura #{reg['n']:04d} reprovada", f"{mencao} não foi aprovado(a) desta vez." + (f"\n**Motivo:** {_ps_txt(motivo, 500)}" if motivo.strip() else ""), 0xED4245)
            await self._enviar(guild, "reprovados", embed=r, allowed_mentions=discord.AllowedMentions(users=True))
            dm = "❌ Sua candidatura à Polícia Civil **não foi aprovada** desta vez." + (f"\nMotivo: {_ps_txt(motivo, 500)}" if motivo.strip() else "") + "\nVocê pode se candidatar novamente."
        if cand:
            try:
                await cand.send(dm)
            except discord.HTTPException:
                pass

    async def aprovar_candidato(self, interaction: discord.Interaction):
        guild, m = interaction.guild, interaction.user
        if not self._eh_recrutador(m):
            await interaction.response.send_message("❌ Apenas a equipe de recrutamento pode decidir.", ephemeral=True)
            return
        reg = self._g(guild)["cand"].get(str(interaction.message.id))
        if not reg or reg["status"] != "pendente":
            await interaction.response.send_message("⚠️ Essa candidatura já foi decidida (ou não achei os dados).", ephemeral=True)
            return
        await interaction.response.defer()
        await self._finalizar_candidatura(guild, interaction.message, reg, True, m)

    async def reprovar_candidato(self, interaction: discord.Interaction, msg_id: int, motivo: str):
        guild, m = interaction.guild, interaction.user
        await interaction.response.defer(ephemeral=True)
        reg = self._g(guild)["cand"].get(str(msg_id))
        if not reg or reg["status"] != "pendente":
            await interaction.followup.send("⚠️ Essa candidatura já foi decidida (ou não achei os dados).", ephemeral=True)
            return
        try:
            msg = await interaction.channel.fetch_message(msg_id)
        except discord.HTTPException:
            await interaction.followup.send("⚠️ Não achei a mensagem da candidatura.", ephemeral=True)
            return
        await self._finalizar_candidatura(guild, msg, reg, False, m, motivo)
        await interaction.followup.send("❌ Candidato reprovado.", ephemeral=True)

    # ══════════════════ PROMOÇÕES ══════════════════
    def _idx_escada(self, member) -> int:
        idx = -1
        for i, k in enumerate(_PS_ESCADA):
            if self._tem(member, [k]):
                idx = i
        return idx

    async def _mudar_posto(self, ctx: commands.Context, membro: discord.Member, delta: int, motivo: str):
        guild, autor = ctx.guild, ctx.author
        if not (self._eh_comando(autor) or self._tem(autor, _PC_GEST)):
            await ctx.send("❌ Apenas o comando e delegados podem promover/rebaixar.")
            return
        if membro.bot or membro.id == autor.id:
            await ctx.send("❌ Alvo inválido.")
            return
        atual = self._idx_escada(membro)
        novo = (0 if atual == -1 else atual + 1) if delta > 0 else atual - 1
        if delta < 0 and atual <= 0:
            await ctx.send("⚠️ Esse policial já está no menor posto da escada (ou não tem posto).")
            return
        if novo >= len(_PS_ESCADA):
            await ctx.send("⚠️ Esse policial já está no maior posto da escada.")
            return
        nivel_autor = len(_PS_ESCADA) if self._eh_comando(autor) else self._idx_escada(autor)
        if nivel_autor <= max(novo, atual if delta < 0 else -1):
            await ctx.send("❌ Você só pode mudar postos abaixo do seu.")
            return
        antigo = self._role(guild, _PS_ESCADA[atual]) if atual >= 0 else None
        novo_role = self._role(guild, _PS_ESCADA[novo])
        try:
            if antigo:
                await membro.remove_roles(antigo, reason=f"{'Promoção' if delta > 0 else 'Rebaixamento'} por {autor}")
            await membro.add_roles(novo_role, reason=f"{'Promoção' if delta > 0 else 'Rebaixamento'} por {autor}")
        except discord.HTTPException as e:
            await ctx.send(f"⚠️ Não consegui alterar os cargos: {getattr(e, 'text', e)}")
            return
        sobe = delta > 0
        e = self._embed("📈 Promoção" if sobe else "📉 Rebaixamento", "", 0x57F287 if sobe else 0xED4245)
        e.add_field(name="👮 Policial", value=membro.mention, inline=True)
        e.add_field(name="📌 Posto", value=f"{antigo.name if antigo else '—'} ➜ **{novo_role.name}**", inline=True)
        e.add_field(name="✍️ Responsável", value=autor.mention, inline=True)
        e.add_field(name="📝 Motivo", value=_ps_txt(motivo, 500), inline=False)
        e.set_thumbnail(url=membro.display_avatar.url)
        await self._enviar(guild, "promocoes", embed=e, allowed_mentions=discord.AllowedMentions.none())
        await ctx.send(f"{'📈' if sobe else '📉'} {membro.mention} agora é **{novo_role.name}**.", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="promover")
    @commands.guild_only()
    async def promover(self, ctx: commands.Context, membro: discord.Member, *, motivo: str = "Não informado"):
        await self._mudar_posto(ctx, membro, +1, motivo)

    @commands.command(name="rebaixar")
    @commands.guild_only()
    async def rebaixar(self, ctx: commands.Context, membro: discord.Member, *, motivo: str = "Não informado"):
        await self._mudar_posto(ctx, membro, -1, motivo)

    @promover.error
    @rebaixar.error
    async def _erro_posto(self, ctx, error):
        if isinstance(error, (commands.MemberNotFound, commands.MissingRequiredArgument)):
            await ctx.send("Uso: `!promover @policial [motivo]` / `!rebaixar @policial [motivo]`", delete_after=8)

    # ══════════════════ BOAS-VINDAS / SAÍDAS / LOGS ══════════════════
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if str(guild.id) not in self.dados["guilds"]:
            return
        if not member.bot:
            reg, ingr = self._canal(guild, "regulamento"), self._canal(guild, "como_ingressar")
            insc = self._canal(guild, "rec_painel")
            e = self._embed("🚔 Bem-vindo(a) à Polícia Civil!", (
                f"Olá, {member.mention}! Que bom ter você aqui.\n\n"
                f"📜 Leia o regulamento: {reg.mention if reg else '—'}\n"
                f"📋 Veja como ingressar: {ingr.mention if ingr else '—'}\n"
                f"📝 Quer ser policial? Candidate-se em {insc.mention if insc else '—'}"
            ), 0x57F287)
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Você é o {guild.member_count}º membro • Polícia Civil")
            await self._enviar(guild, "boas_vindas", content=member.mention, embed=e,
                               allowed_mentions=discord.AllowedMentions(users=[member]))
        log = discord.Embed(title="📥 Membro entrou" if not member.bot else "🤖 Bot adicionado", color=0x57F287, timestamp=discord.utils.utcnow())
        log.description = f"{member.mention} (`{member.id}`)"
        log.add_field(name="Conta criada", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        log.add_field(name="Membros", value=str(guild.member_count), inline=True)
        log.set_thumbnail(url=member.display_avatar.url)
        await self._log(guild, "log_membros", log)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if str(guild.id) not in self.dados["guilds"]:
            return
        # turno aberto? fecha pra não ficar contando horas de quem saiu
        try:
            await self._fechar_sessao(guild, member.id, None, saiu=True)
        except Exception as e:
            _log_erro("fechar_sessao_saida", e)
        if not member.bot:
            e = self._embed("👋 Até logo!", f"**{_ps_txt(member.display_name, 60)}** deixou a corporação.", 0x99AAB5)
            e.set_thumbnail(url=member.display_avatar.url)
            await self._enviar(guild, "saidas", embed=e, allowed_mentions=discord.AllowedMentions.none())
        log = discord.Embed(title="📤 Membro saiu", color=0xED4245, timestamp=discord.utils.utcnow())
        log.description = f"{member.mention} (`{member.id}`) — {_ps_txt(str(member), 80)}"
        if member.joined_at:
            log.add_field(name="Ficou por", value=_ps_dur(time.time() - member.joined_at.timestamp()), inline=True)
        cargos = [r.mention for r in member.roles if not r.is_default()]
        log.add_field(name="Cargos", value=(" ".join(cargos) or "—")[:1024], inline=False)
        log.set_thumbnail(url=member.display_avatar.url)
        await self._log(guild, "log_membros", log)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot or str(message.guild.id) not in self.dados["guilds"]:
            return
        e = discord.Embed(title="🗑️ Mensagem apagada", color=0xED4245, timestamp=discord.utils.utcnow())
        e.add_field(name="Autor", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        e.add_field(name="Canal", value=message.channel.mention, inline=True)
        e.add_field(name="Conteúdo", value=_ps_txt(message.content or "*(sem texto)*"), inline=False)
        if message.attachments:
            e.add_field(name="Anexos", value=str(len(message.attachments)), inline=True)
        await self._log(message.guild, "log_msg", e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        if str(after.guild.id) not in self.dados["guilds"]:
            return
        e = discord.Embed(title="✏️ Mensagem editada", color=0xFEE75C, timestamp=discord.utils.utcnow())
        e.add_field(name="Autor", value=f"{after.author.mention} (`{after.author.id}`)", inline=True)
        e.add_field(name="Canal", value=f"{after.channel.mention} — [ir]({after.jump_url})", inline=True)
        e.add_field(name="Antes", value=_ps_txt(before.content or "—", 500), inline=False)
        e.add_field(name="Depois", value=_ps_txt(after.content or "—", 500), inline=False)
        await self._log(after.guild, "log_msg", e)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or before.channel == after.channel or str(member.guild.id) not in self.dados["guilds"]:
            return
        if before.channel is None:
            titulo, cor, desc = "🔊 Entrou na voz", 0x57F287, f"{member.mention} entrou em **{after.channel.name}**"
        elif after.channel is None:
            titulo, cor, desc = "🔇 Saiu da voz", 0xED4245, f"{member.mention} saiu de **{before.channel.name}**"
        else:
            titulo, cor, desc = "🔀 Trocou de sala", 0xFEE75C, f"{member.mention}: **{before.channel.name}** ➜ **{after.channel.name}**"
        await self._log(member.guild, "log_voz", discord.Embed(title=titulo, description=desc, color=cor, timestamp=discord.utils.utcnow()))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild
        if str(guild.id) not in self.dados["guilds"]:
            return
        ignorar = {r.id for k in ("servico", "fora") if (r := self._role(guild, k)) is not None}
        ganhou = [r for r in after.roles if r not in before.roles and r.id not in ignorar]
        perdeu = [r for r in before.roles if r not in after.roles and r.id not in ignorar]
        if ganhou or perdeu or before.nick != after.nick:
            e = discord.Embed(title="🛡️ Membro atualizado", description=after.mention, color=_PS_COR, timestamp=discord.utils.utcnow())
            if ganhou:
                e.add_field(name="➕ Cargos adicionados", value=" ".join(r.mention for r in ganhou)[:1024], inline=False)
            if perdeu:
                e.add_field(name="➖ Cargos removidos", value=" ".join(r.mention for r in perdeu)[:1024], inline=False)
            if before.nick != after.nick:
                e.add_field(name="Apelido", value=f"{_ps_txt(before.nick or '—', 60)} ➜ {_ps_txt(after.nick or '—', 60)}", inline=False)
            await self._log(guild, "log_cargos", e)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if str(guild.id) in self.dados["guilds"]:
            await self._log(guild, "log_mod", discord.Embed(title="🔨 Membro banido", description=f"{user} (`{user.id}`)", color=0xED4245, timestamp=discord.utils.utcnow()))

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if str(guild.id) in self.dados["guilds"]:
            await self._log(guild, "log_mod", discord.Embed(title="♻️ Banimento removido", description=f"{user} (`{user.id}`)", color=0x57F287, timestamp=discord.utils.utcnow()))

    # ── sugestões: reações de voto + thread de discussão ──
    @commands.Cog.listener("on_message")
    async def _sugestoes(self, message: discord.Message):
        if message.guild is None or message.author.bot or str(message.guild.id) not in self.dados["guilds"]:
            return
        ch = self._canal(message.guild, "sugestoes")
        if ch is None or message.channel.id != ch.id or message.content.startswith(("!", "/")):
            return
        try:
            await message.add_reaction("👍")
            await message.add_reaction("👎")
            await message.create_thread(name=f"Sugestão de {message.author.display_name}"[:90], auto_archive_duration=1440)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
    await bot.add_cog(PoliciaSistema(bot))
