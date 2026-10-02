import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import re
import time
import unicodedata
from datetime import datetime, timezone

from cogs.backup import ler, salvar
from cogs.players import CARGOS as PLAYER_CARGOS, aplicar_cargo_rank
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

RANK_IDS = set(CARGO_RANKS.values())

PLATAFORMAS = ["PC", "Xbox", "PlayStation", "Switch"]

PEAK_RANKS = [
    "Bronze", "Prata", "Ouro", "Platina",
    "Diamante", "Champion", "Grand Champion", "Supersonic Legend",
]
DIVISOES = ["Divisão 1", "Divisão 2", "Divisão 3"]

TEMPOS_JOGANDO = ["Menos de 1 ano", "1 a 2 anos", "2 a 4 anos", "Mais de 4 anos"]


HABILIDADES = ["Programação", "Designer", "Roteiro", "Editor de vídeo", "Administração"]


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

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        nick_valor = self.nick.value.strip()

        self.cog.salvar_resposta(membro.id, "nick", nick_valor)

        aviso_nick = ""
        try:
            await membro.edit(nick=nick_valor, reason="Whitelist — nick informado")
        except discord.Forbidden:
            aviso_nick = "\n⚠️ Não consegui atualizar seu apelido (permissão), mas seguimos!"

        await interaction.response.send_message(
            f"✅ Nick registrado: **{nick_valor}**{aviso_nick}",
        )
        await asyncio.sleep(5)
        await self.cog.enviar_pergunta(interaction.channel, membro, "idioma")


class PerguntasAbertasModal(discord.ui.Modal, title="Whitelist — Perguntas"):
    # pra add uma pergunta nova de texto livre é só criar outro TextInput
    # aqui embaixo, tipo o do tiktok, só troca label/placeholder/max_length
    # modal aceita até 5 campos, então dá de sobra
    tiktok = discord.ui.TextInput(
        label="Qual o link da sua conta do TikTok?",
        placeholder="Ex: https://www.tiktok.com/@seuusuario",
        style=discord.TextStyle.short,
        max_length=200,
        required=True,
    )

    def __init__(self, cog: "Whitelist"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        ja = self.cog.dados.get(str(membro.id), {}).get("respostas", {}).get("tiktok")
        if ja:
            await interaction.response.send_message("⚠️ Você já respondeu essa pergunta.", ephemeral=True)
            return
        self.cog.salvar_resposta(membro.id, "tiktok", self.tiktok.value.strip())
        # e aqui salva a resposta do campo novo, mesma ideia, só troca a
        # chave (o nome que fica salvo no json, tipo "tiktok") e o valor
        # pra pegar do campo que vc criou lá em cima

        await interaction.response.send_message("✅ Respostas registradas!")
        await self.cog.enviar_pergunta(interaction.channel, membro, "duvidas")


class DesistirButton(discord.ui.Button):
    """Botão reutilizável de 'desistir', adicionado nas etapas intermediárias
    da whitelist (depois da primeira tela) pra pessoa poder desistir a
    qualquer momento, não só no início."""
    def __init__(self):
        super().__init__(label="🚫 Desistir", style=discord.ButtonStyle.secondary, custom_id="wl_desistir_etapa", row=4)

    async def callback(self, interaction: discord.Interaction):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.pedir_confirmacao_desistencia(interaction)


class AbrirPerguntasView(discord.ui.View):
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
        if not await self.cog.checar_dono(interaction):
            return
        await _travar_mensagem(interaction)
        membro = interaction.user
        valor = self.values[0]
        self.cog.salvar_resposta(membro.id, self.step, valor)

        if self.step == "idioma":
            guild = interaction.guild
            cargo_ingles = guild.get_role(CARGO_IDIOMA_INGLES_ID)


            falantes_ingles = sum(
                1 for m in (cargo_ingles.members if cargo_ingles else [])
                if not m.bot and m.id != membro.id
            )
            total_humanos = sum(1 for m in guild.members if not m.bot and m.id != membro.id)

            if valor == "Inglês":
                contagem = falantes_ingles
            else:
                contagem = total_humanos - falantes_ingles

            cargo_msg = ""
            if valor == "Inglês":
                if cargo_ingles:
                    try:
                        await membro.add_roles(cargo_ingles, reason="Whitelist — idioma Inglês selecionado")
                        cargo_msg = f"\n🏷️ Cargo {cargo_ingles.mention} atribuído!"
                    except discord.Forbidden:
                        cargo_msg = "\n⚠️ Não consegui atribuir o cargo de idioma (permissão)."
                else:
                    cargo_msg = "\n⚠️ Cargo de idioma configurado não foi encontrado no servidor."

            await interaction.response.send_message(
                f"✅ Idioma registrado: **{valor}**.\n"
                f"🌐 Mais **{contagem}** pessoa(s) falam o mesmo idioma que você.{cargo_msg}"
            )
        elif self.step == "rank":
            if valor in RANK_TIERS_COM_DIVISAO:
                await interaction.response.send_message(
                    f"✅ Rank registrado: **{valor}**. Agora escolhe a divisão! 🔢"
                )
                await self.cog.enviar_pergunta(interaction.channel, membro, "rank_divisao")
            else:
                # Super Sonic Legend não tem divisão, já vai direto pra próxima etapa
                await interaction.response.send_message(
                    f"✅ Rank registrado: **{valor}**.\n*(o cargo só é aplicado se a whitelist for aprovada)*"
                )
                await self.cog.enviar_pergunta(interaction.channel, membro, "plataforma")
            return

        elif self.step == "rank_divisao":
            registro = self.cog.dados.get(str(membro.id), {})
            tier = registro.get("respostas", {}).get("rank", "")
            rank_completo = f"{tier} {valor}".strip()
            self.cog.salvar_resposta(membro.id, "rank", rank_completo)
            await interaction.response.send_message(
                f"✅ Divisão registrada: **{rank_completo}**.\n*(o cargo só é aplicado se a whitelist for aprovada)*"
            )
            await self.cog.enviar_pergunta(interaction.channel, membro, "plataforma")
            return

        else:
            await interaction.response.send_message(f"✅ Resposta registrada: **{valor}**")


        if self.step == "peak_rank" and valor == "Supersonic Legend":
            self.cog.salvar_resposta(membro.id, "peak_div", "—")
            await self.cog.enviar_pergunta(interaction.channel, membro, "tempo")
            return


        if self.step == "tem_tiktok" and valor == "Não":
            self.cog.salvar_resposta(membro.id, "tiktok", "Não possui")
            await self.cog.enviar_pergunta(interaction.channel, membro, "habilidades")
            return

        if self.prox_step:
            await self.cog.enviar_pergunta(interaction.channel, membro, self.prox_step)


class EscolhaView(discord.ui.View):
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
        await _travar_mensagem(interaction)
        membro = interaction.user
        valor = ", ".join(self.values)
        cog.salvar_resposta(membro.id, "habilidades", valor)
        await interaction.response.send_message(f"✅ Habilidade(s) registrada(s): **{valor}**")
        await cog.prosseguir_apos_habilidades(interaction.channel, membro)


class HabilidadesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HabilidadesSelect())
        self.add_item(DesistirButton())

    @discord.ui.button(label="⏭️ Pular", style=discord.ButtonStyle.secondary, custom_id="wl_pular_habilidades", row=1)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: "Whitelist" = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        await _travar_mensagem(interaction)
        membro = interaction.user
        cog.salvar_resposta(membro.id, "habilidades", "Nenhuma")
        await interaction.response.send_message("⏭️ Pergunta pulada — nenhuma habilidade registrada.")
        await cog.prosseguir_apos_habilidades(interaction.channel, membro)


class ComecarWhitelistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚀 Começar Whitelist", style=discord.ButtonStyle.success, custom_id="wl_comecar")
    async def comecar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        if not await cog.checar_dono(interaction):
            return
        if cog.dados.get(str(interaction.user.id), {}).get("respostas", {}).get("nick"):
            await interaction.response.send_message("⚠️ Você já começou sua whitelist — siga as perguntas abaixo. 👇", ephemeral=True)
            return
        await interaction.response.send_modal(NickModal(cog))

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


class FinalizarWhitelistView(discord.ui.View):
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


class RevisaoWhitelistView(discord.ui.View):
    """Botões de revisão (Visualizada / Aprovar / Recusar [+ Abrir chat]).

    IMPORTANTE: quem é o candidato NÃO fica guardado aqui. Os botões são
    persistentes (todos usam o mesmo custom_id) e, depois de um restart, o
    Discord entrega o clique pra uma única instância registrada — então o
    candidato é descoberto na hora do clique, pela mensagem ou pelo canal
    (ver Whitelist.membro_id_da_interacao). Antes isso aprovava/recusava a
    pessoa errada quando havia mais de uma whitelist pendente.

    Passando guild_id e canal_id aparece o botão 📂 que abre o chat da
    whitelist (usado na mensagem do canal de log)."""
    def __init__(self, guild_id: int | None = None, canal_id: int | None = None):
        super().__init__(timeout=None)
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


class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("whitelist")
        preencher_stats_se_vazio(self.dados)
        self.limpeza_canais.start()
        self.incentivo_whitelist.start()

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
        await self._garantir_acesso_staff(interaction.channel)
        await interaction.response.send_message(
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
        await self.criar_canal_whitelist(member)

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
        (Champion). Troca os cargos de rank antigos."""
        cargo = guild.get_role(CARGO_RANKS.get(rank_nome, 0))
        if cargo is None:
            return f"⚠️ Não achei o cargo do rank **{rank_nome}**."
        try:
            await aplicar_cargo_rank(membro, cargo, "Whitelist — rank aplicado")
        except discord.Forbidden:
            return "⚠️ Não tenho permissão pra dar o cargo de rank."
        return None

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


    @staticmethod
    def _config_escolha() -> dict:
        """Etapas de múltipla escolha: (opções, placeholder, próxima etapa, emojis)."""
        return {
            "idioma":       (IDIOMAS, "Escolha seu idioma...", "rank", IDIOMA_EMOJIS),
            "rank":         (RANK_TIERS_ORDEM, "Escolha seu rank atual...", "rank_divisao", RANK_TIER_EMOJIS),
            "rank_divisao": (RANK_DIVISOES_OPCOES, "Escolha a divisão...", "plataforma", None),
            "plataforma":   (PLATAFORMAS, "Escolha sua plataforma...", "peak_rank", None),
            "peak_rank":    (PEAK_RANKS, "Escolha o maior rank já alcançado...", "peak_div", None),
            "peak_div":     (DIVISOES, "Escolha a divisão...", "tempo", None),
            "tempo":        (TEMPOS_JOGANDO, "Escolha há quanto tempo joga...", "microfone", None),
            "microfone":    (["Sim", "Não"], "Você tem microfone?", "ativo", None),
            "ativo":        (["Sim", "Não"], "Você vai ser ativo?", "tem_tiktok", None),
            "tem_tiktok":   (["Sim", "Não"], "Você tem TikTok?", "habilidades", None),
        }

    def _view_escolha(self, step: str) -> "EscolhaView":
        opcoes, placeholder, prox, emojis = self._config_escolha()[step]
        return EscolhaView(self, step, opcoes, placeholder, prox, emojis=emojis)

    async def enviar_pergunta(self, canal: discord.TextChannel, membro: discord.Member, step: str):
        if step == "idioma":
            view = self._view_escolha("idioma")
            await canal.send("🌐 **Qual é a sua linguagem?**\n(Português ou Inglês — só pode escolher uma)", view=view)

        elif step == "rank":
            view = self._view_escolha("rank")
            await canal.send("🎮 **Qual o seu rank atual no Rocket League?**", view=view)

        elif step == "rank_divisao":
            registro = self.dados.get(str(membro.id), {})
            tier = registro.get("respostas", {}).get("rank", "")
            view = self._view_escolha("rank_divisao")
            await canal.send(f"🔢 **Qual divisão do seu rank {tier}?** (1, 2 ou 3)", view=view)

        elif step == "plataforma":
            view = self._view_escolha("plataforma")
            await canal.send("🖥️ **Em qual plataforma você joga?**", view=view)

        elif step == "peak_rank":
            view = self._view_escolha("peak_rank")
            await canal.send("🏆 **Qual o maior rank que você já alcançou?**", view=view)

        elif step == "peak_div":
            view = self._view_escolha("peak_div")
            await canal.send("🔢 **E qual divisão desse rank?**", view=view)

        elif step == "tempo":
            view = self._view_escolha("tempo")
            await canal.send("⏱️ **Há quanto tempo você joga Rocket League?**", view=view)

        elif step == "microfone":
            view = self._view_escolha("microfone")
            await canal.send("🎤 **Você tem microfone pra jogar?**", view=view)

        elif step == "ativo":
            view = self._view_escolha("ativo")
            await canal.send("📈 **Você pretende ser um membro ativo na equipe?**", view=view)

        elif step == "tem_tiktok":
            view = self._view_escolha("tem_tiktok")
            await canal.send("🎵 **Você tem conta no TikTok?**", view=view)

        elif step == "habilidades":
            embed = discord.Embed(
                title="🛠️ Alguma habilidade extra?",
                description=(
                    "Você tem alguma dessas habilidades? **(opcional, pode selecionar mais de uma ou pular)**\n\n"
                    + "\n".join(f"• {h}" for h in HABILIDADES)
                ),
                color=0x5865F2,
            )
            await canal.send(embed=embed, view=HabilidadesView())

        elif step == "perguntas_abertas":
            embed = discord.Embed(
                title="📝 Última pergunta",
                description=(
                    "Só falta mais uma coisa. Clica no botão abaixo pra abrir o formulário:\n\n"
                    "• Qual o link da sua conta do TikTok?"
                    # se add pergunta nova no modal, bota ela aqui também
                    # nessa listinha, só copia o padrão de cima
                ),
                color=0x5865F2,
            )
            await canal.send(embed=embed, view=AbrirPerguntasView(self))

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
            await canal.send(embed=embed, view=FinalizarWhitelistView())


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
        embed_resumo.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
        embed_resumo.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
        embed_resumo.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
        embed_resumo.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
        embed_resumo.add_field(name="Maior rank", value=f"{r.get('peak_rank','—')} ({r.get('peak_div','—')})", inline=True)
        embed_resumo.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
        embed_resumo.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
        embed_resumo.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
        embed_resumo.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
        embed_resumo.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)
        # add_field da pergunta nova entra aqui tb, mesmo esquema
        embed_resumo.set_footer(text=f"ID: {membro.id}")
        await interaction.channel.send(embed=embed_resumo)

        embed_revisao = discord.Embed(
            title="🔎 Whitelist aguardando revisão",
            description=f"Analisa as respostas de {membro.mention} e decide abaixo.\n(apenas a **staff da whitelist**)",
            color=0xFEE75C,
        )
        msg_revisao = await interaction.channel.send(embed=embed_revisao, view=RevisaoWhitelistView())
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
                embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
                embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
                embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
                embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
                embed.add_field(name="Maior rank", value=f"{r.get('peak_rank','—')} ({r.get('peak_div','—')})", inline=True)
                embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
                embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
                embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
                embed.add_field(name="TikTok", value=r.get("tiktok", "—"), inline=False)
                embed.add_field(name="Habilidades", value=r.get("habilidades", "—"), inline=False)
                embed.set_footer(text=f"ID: {membro.id}")
                try:
                    # mesmos botões de revisão + 📂 "Abrir chat da whitelist" ao lado
                    msg_log = await canal_log.send(embed=embed, view=RevisaoWhitelistView(guild.id, interaction.channel.id))
                    revisao_msgs.append({"canal_id": canal_log.id, "msg_id": msg_log.id})
                except discord.HTTPException as e:
                    print(f"[WHITELIST] ⚠️ Não consegui enviar a revisão pro canal de log: {e}")

        registro["revisao_msgs"] = revisao_msgs
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
            erro = await self.dar_cargo_rank(guild, membro, respostas["rank"])
            if erro:
                avisos.append(erro)
        if membro and respostas.get("plataforma"):
            erro = await self.dar_cargo_plataforma(guild, membro, respostas["plataforma"])
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
        plataforma="Plataforma que o jogador usa",
        tempo="Há quanto tempo joga Rocket League",
        microfone="Se o jogador tem microfone",
        ativo="Se o jogador pretende ser ativo na equipe",
        tem_tiktok="Se o jogador tem TikTok",
        tiktok="Link do TikTok (se tiver)",
        habilidades="Habilidades extras (texto livre, ex: Designer, Editor de vídeo)",
    )
    @app_commands.choices(
        rank=[app_commands.Choice(name=r, value=r) for r in CARGO_RANKS.keys()],
        idioma=[app_commands.Choice(name=i, value=i) for i in IDIOMAS],
        maior_rank=[app_commands.Choice(name=r, value=r) for r in PEAK_RANKS],
        peak_div=[app_commands.Choice(name=d, value=d) for d in DIVISOES],
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

        campos = [nick, idioma, rank, maior_rank, peak_div, plataforma, tempo, microfone, ativo, tem_tiktok, tiktok, habilidades]
        if not any(campos):
            await interaction.response.send_message(
                "⚠️ Informe pelo menos um campo pra alterar.",
                ephemeral=True,
            )
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
            registro["respostas"]["tiktok"] = tiktok

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
