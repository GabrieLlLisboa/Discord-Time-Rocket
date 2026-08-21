import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import re
import time

from cogs.backup import ler, salvar
from cogs.players import CARGOS as PLAYER_CARGOS
from cogs import mod_utils as mu


CARGO_RANKS = {c["nome"]: c["id"] for c in PLAYER_CARGOS if c["secao"] == "rank"}


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


CARGOS_QUE_VEEM_WHITELIST = {
    1511895253777649704,
    1511894837790769204,
    1523835085475020932,
}

RANK_IDS = set(CARGO_RANKS.values())

PLATAFORMAS = ["PC", "Xbox", "PlayStation", "Switch"]

PEAK_RANKS = [
    "Bronze", "Prata", "Ouro", "Platina",
    "Diamante", "Champion", "Grand Champion", "Supersonic Legend",
]
DIVISOES = ["Divisão 1", "Divisão 2", "Divisão 3"]

TEMPOS_JOGANDO = ["Menos de 1 ano", "1 a 2 anos", "2 a 4 anos", "Mais de 4 anos"]


HABILIDADES = ["Programação", "Designer", "Roteiro", "Editor de vídeo", "Administração"]


def _slug(nome: str) -> str:
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
        await interaction.response.send_modal(PerguntasAbertasModal(self.cog))


class EscolhaSelect(discord.ui.Select):
    def __init__(self, cog: "Whitelist", step: str, opcoes: list[str], placeholder: str, prox_step: str | None, emojis: dict | None = None):
        options = [
            discord.SelectOption(label=o, emoji=(emojis or {}).get(o))
            for o in opcoes
        ]
        super().__init__(placeholder=placeholder, options=options)
        self.cog = cog
        self.step = step
        self.prox_step = prox_step

    async def callback(self, interaction: discord.Interaction):
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
            await interaction.response.send_message(
                f"✅ Rank registrado: **{valor}**.\n*(o cargo só é aplicado se a whitelist for aprovada)*"
            )
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
        )

    async def callback(self, interaction: discord.Interaction):
        cog: "Whitelist" = interaction.client.get_cog("Whitelist")
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
        if interaction.channel.name != f"whitelist-{_slug(interaction.user.name)}" and\
           not interaction.channel.name.startswith("whitelist-"):
            await interaction.response.send_message("❌ Use isso no seu canal de whitelist.", ephemeral=True)
            return
        await interaction.response.send_modal(NickModal(cog))

    @discord.ui.button(label="🚫 Desistir", style=discord.ButtonStyle.secondary, custom_id="wl_desistir")
    async def desistir(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.pedir_confirmacao_desistencia(interaction)

    @discord.ui.button(label="🗑️ Cancelar/Fechar (staff)", style=discord.ButtonStyle.danger, custom_id="wl_cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cargos = {r.id for r in interaction.user.roles}
        if not (mu.eh_super_admin(interaction.user.id) or interaction.user.guild_permissions.administrator or cargos & CARGOS_QUE_VEEM_WHITELIST):
            await interaction.response.send_message("❌ Apenas staff pode fechar.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        cog.marcar_cancelada(interaction.channel.id, motivo="staff")
        await interaction.response.send_message("🔒 Fechando canal em 3 segundos...")
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Whitelist cancelada por {interaction.user}")


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


def _checar_admin(interaction: discord.Interaction) -> bool:
    return mu.eh_super_admin(interaction.user.id) or interaction.user.guild_permissions.administrator


class RevisaoWhitelistView(discord.ui.View):
    def __init__(self, membro_id: int):
        super().__init__(timeout=None)
        self.membro_id = membro_id

    @discord.ui.button(label="👀 Marcar como Visualizada", style=discord.ButtonStyle.secondary, custom_id="wl_visualizar")
    async def visualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só administradores podem revisar whitelists.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.marcar_visualizada(interaction, self.membro_id)

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success, custom_id="wl_aprovar")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só administradores podem revisar whitelists.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        ephemeral, mensagem = await cog.aprovar_core(interaction.guild, self.membro_id, interaction.user, interaction.channel)
        await interaction.response.send_message(mensagem, ephemeral=ephemeral)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger, custom_id="wl_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só administradores podem revisar whitelists.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        ephemeral, mensagem = await cog.recusar_core(interaction.guild, self.membro_id, interaction.user, interaction.channel)
        await interaction.response.send_message(mensagem, ephemeral=ephemeral)


class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("whitelist")
        self.limpeza_canais.start()
        self.incentivo_whitelist.start()

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
                    await canal.delete(reason="Whitelist aprovada — canal removido automaticamente após 10 minutos")
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
        uid = str(user_id)
        registro = self.dados.setdefault(uid, {"respostas": {}, "status": "em_andamento"})
        registro["respostas"][chave] = valor
        salvar("whitelist", self.dados)


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

        nome_canal = f"whitelist-{_slug(member.name)}"

        existente = discord.utils.get(guild.text_channels, name=nome_canal)
        if existente:
            return existente

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


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
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


    async def dar_cargo_rank(self, guild: discord.Guild, membro: discord.Member, rank_nome: str) -> str | None:
        cargo = guild.get_role(CARGO_RANKS.get(rank_nome, 0))
        if cargo is None:
            return f"⚠️ Não achei o cargo do rank **{rank_nome}**."
        cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS and r.id != cargo.id]
        try:
            if cargos_rank_atuais:
                await membro.remove_roles(*cargos_rank_atuais, reason="Whitelist aprovada — troca de rank")
            if cargo not in membro.roles:
                await membro.add_roles(cargo, reason="Whitelist aprovada — rank aplicado")
        except discord.Forbidden:
            return "⚠️ Não tenho permissão pra dar o cargo de rank."
        return None


    async def prosseguir_apos_habilidades(self, canal: discord.TextChannel, membro: discord.Member):
        registro = self.dados.get(str(membro.id), {})
        tem_tiktok = registro.get("respostas", {}).get("tem_tiktok")
        if tem_tiktok == "Sim":
            await self.enviar_pergunta(canal, membro, "perguntas_abertas")
        else:
            await self.enviar_pergunta(canal, membro, "duvidas")


    async def enviar_pergunta(self, canal: discord.TextChannel, membro: discord.Member, step: str):
        if step == "idioma":
            view = EscolhaView(self, "idioma", IDIOMAS, "Escolha seu idioma...", "rank", emojis=IDIOMA_EMOJIS)
            await canal.send("🌐 **Qual é a sua linguagem?**\n(Português ou Inglês — só pode escolher uma)", view=view)

        elif step == "rank":
            view = EscolhaView(self, "rank", list(CARGO_RANKS.keys()), "Escolha seu rank atual...", "plataforma")
            await canal.send("🎮 **Qual o seu rank atual no Rocket League?**", view=view)

        elif step == "plataforma":
            view = EscolhaView(self, "plataforma", PLATAFORMAS, "Escolha sua plataforma...", "peak_rank")
            await canal.send("🖥️ **Em qual plataforma você joga?**", view=view)

        elif step == "peak_rank":
            view = EscolhaView(self, "peak_rank", PEAK_RANKS, "Escolha o maior rank já alcançado...", "peak_div")
            await canal.send("🏆 **Qual o maior rank que você já alcançou?**", view=view)

        elif step == "peak_div":
            view = EscolhaView(self, "peak_div", DIVISOES, "Escolha a divisão...", "tempo")
            await canal.send("🔢 **E qual divisão desse rank?**", view=view)

        elif step == "tempo":
            view = EscolhaView(self, "tempo", TEMPOS_JOGANDO, "Escolha há quanto tempo joga...", "microfone")
            await canal.send("⏱️ **Há quanto tempo você joga Rocket League?**", view=view)

        elif step == "microfone":
            view = EscolhaView(self, "microfone", ["Sim", "Não"], "Você tem microfone?", "ativo")
            await canal.send("🎤 **Você tem microfone pra jogar?**", view=view)

        elif step == "ativo":
            view = EscolhaView(self, "ativo", ["Sim", "Não"], "Você vai ser ativo?", "tem_tiktok")
            await canal.send("📈 **Você pretende ser um membro ativo na equipe?**", view=view)

        elif step == "tem_tiktok":
            view = EscolhaView(self, "tem_tiktok", ["Sim", "Não"], "Você tem TikTok?", "habilidades")
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
        membro = interaction.user
        guild = interaction.guild
        registro = self.dados.get(str(membro.id))
        if not registro:
            await interaction.response.send_message("⚠️ Não achei seus dados de whitelist. Chama a staff.", ephemeral=True)
            return

        registro["status"] = "pendente"
        salvar("whitelist", self.dados)

        await interaction.response.send_message(
            "📨 **Suas respostas foram enviadas!** Um administrador vai revisar e te avisar por aqui assim que decidir. Aguenta aí! ⏳"
        )


        try:
            await interaction.channel.set_permissions(membro, send_messages=False, view_channel=True)
        except discord.Forbidden:
            pass

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
            description=f"Analisa as respostas de {membro.mention} e decide abaixo.\n(apenas **administradores**)",
            color=0xFEE75C,
        )
        await interaction.channel.send(embed=embed_revisao, view=RevisaoWhitelistView(membro.id))


        if CANAL_LOG_WHITELIST_ID:
            canal_log = self.bot.get_channel(CANAL_LOG_WHITELIST_ID)
            if canal_log:
                embed = discord.Embed(title=f"📋 Whitelist enviada para análise — {membro}", color=0xFEE75C)
                embed.set_thumbnail(url=membro.display_avatar.url)
                embed.add_field(name="Idioma", value=r.get("idioma", "—"), inline=True)
                embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
                embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
                embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
                embed.add_field(name="Maior rank", value=f"{r.get('peak_rank','—')} ({r.get('peak_div','—')})", inline=True)
                embed.add_field(name="Tempo jogando", value=r.get("tempo", "—"), inline=True)
                embed.add_field(name="Microfone", value=r.get("microfone", "—"), inline=True)
                embed.add_field(name="Ativo?", value=r.get("ativo", "—"), inline=True)
                # esse aqui (log) nem tem os campos de tiktok/habilidades ainda
                # se for add a pergunta nova, bota ela junto com esses dois que
                # tão faltando, mesmo padrão dos outros embeds
                embed.set_footer(text=f"ID: {membro.id}")
                await canal_log.send(embed=embed)


    async def marcar_visualizada(self, interaction: discord.Interaction, membro_id: int):
        registro = self.dados.get(str(membro_id))
        if not registro:
            await interaction.response.send_message("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return
        registro["status"] = "visualizada"
        registro["visualizado_por_id"] = interaction.user.id
        registro["visualizado_por_nome"] = str(interaction.user)
        salvar("whitelist", self.dados)
        await self.atualizar_status_board(interaction.guild, membro_id)
        await interaction.response.send_message(
            f"👀 Marcada como em análise por {interaction.user.mention}. "
            f"A partir de agora, só {interaction.user.mention} pode aprovar ou recusar essa whitelist."
        )


    async def aprovar_core(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, canal: discord.TextChannel) -> tuple[bool, str]:
        registro = self.dados.get(str(membro_id))
        if not registro:
            return True, "⚠️ Não achei os dados dessa whitelist."

        if registro.get("status") in ("aprovada", "recusada"):
            acao = "aprovada" if registro["status"] == "aprovada" else "recusada"
            quem = registro.get("decidido_por_nome", "outro administrador")
            return True, f"⚠️ Essa whitelist já foi **{acao}** por **{quem}** — ninguém mais precisa mexer nela."

        visualizado_por_id = registro.get("visualizado_por_id")
        if visualizado_por_id is not None and visualizado_por_id != autor.id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            return True, f"⚠️ Essa whitelist foi marcada como em análise por **{nome}** — só ela(e) pode aprovar ou recusar."


        registro["status"] = "aprovada"
        registro["decidido_por_nome"] = str(autor)
        registro["decidido_por_id"] = autor.id
        salvar("whitelist", self.dados)

        membro = guild.get_member(membro_id)
        cargo_sem_acesso = guild.get_role(CARGO_SEM_ACESSO_ID)
        if membro and cargo_sem_acesso and cargo_sem_acesso in membro.roles:
            try:
                await membro.remove_roles(cargo_sem_acesso, reason=f"Whitelist aprovada por {autor}")
            except discord.Forbidden:
                pass

        aviso_rank = ""
        rank_nome = registro["respostas"].get("rank")
        if membro and rank_nome:
            erro = await self.dar_cargo_rank(guild, membro, rank_nome)
            if erro:
                aviso_rank = f"\n{erro}"

        await self.atualizar_status_board(guild, membro_id)

        mensagem = (
            f"✅ **Whitelist aprovada por {autor.mention}!** "
            f"{membro.mention if membro else ''} os canais do servidor já estão liberados. Bem-vindo(a)! 🚀{aviso_rank}\n"
            f"*(este canal vai ser apagado automaticamente em 10 minutos)*"
        )


        if membro:
            try:
                await canal.set_permissions(membro, overwrite=None)
            except discord.Forbidden:
                pass


        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        return False, mensagem


    async def recusar_core(self, guild: discord.Guild, membro_id: int, autor: discord.abc.User, canal: discord.TextChannel) -> tuple[bool, str]:
        registro = self.dados.get(str(membro_id))
        if not registro:
            return True, "⚠️ Não achei os dados dessa whitelist."

        if registro.get("status") in ("aprovada", "recusada"):
            acao = "aprovada" if registro["status"] == "aprovada" else "recusada"
            quem = registro.get("decidido_por_nome", "outro administrador")
            return True, f"⚠️ Essa whitelist já foi **{acao}** por **{quem}** — ninguém mais precisa mexer nela."

        visualizado_por_id = registro.get("visualizado_por_id")
        if visualizado_por_id is not None and visualizado_por_id != autor.id:
            nome = registro.get("visualizado_por_nome", "outro administrador")
            return True, f"⚠️ Essa whitelist foi marcada como em análise por **{nome}** — só ela(e) pode aprovar ou recusar."


        registro["status"] = "recusada"
        registro["decidido_por_nome"] = str(autor)
        registro["decidido_por_id"] = autor.id
        salvar("whitelist", self.dados)

        membro = guild.get_member(membro_id)

        aviso_kick = ""
        if membro:
            try:
                await membro.kick(reason=f"Whitelist recusada por {autor}")
            except discord.Forbidden:
                aviso_kick = "\n⚠️ Não consegui expulsar o membro (falta permissão/hierarquia de cargo) — remova manualmente."
        else:
            aviso_kick = "\n⚠️ O membro não está mais no servidor."

        await self.atualizar_status_board(guild, membro_id)


        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        mensagem = (
            f"❌ **Whitelist recusada por {autor.mention}.** "
            f"{membro.mention if membro else 'O membro'} foi removido do servidor automaticamente.{aviso_kick}\n"
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
    @commands.has_permissions(administrator=True)
    async def whitelist_manual(self, ctx: commands.Context, membro: discord.Member):
        canal = await self.criar_canal_whitelist(membro)
        await ctx.send(f"✅ Canal de whitelist pronto: {canal.mention}", delete_after=6)

    @whitelist_manual.error
    async def whitelist_manual_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Não achei esse membro.", delete_after=5)


    @commands.command(name="aprovar-whitelist")
    @commands.has_permissions(administrator=True)
    async def aprovar_whitelist_cmd(self, ctx: commands.Context):
        membro_id = self._membro_id_do_canal(ctx.channel.id)
        if membro_id is None:
            await ctx.send("⚠️ Esse comando só funciona dentro do canal de whitelist de um membro.", delete_after=8)
            return
        _, mensagem = await self.aprovar_core(ctx.guild, membro_id, ctx.author, ctx.channel)
        await ctx.send(mensagem)

    @aprovar_whitelist_cmd.error
    async def aprovar_whitelist_cmd_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)

    @commands.command(name="reprovar-whitelist")
    @commands.has_permissions(administrator=True)
    async def reprovar_whitelist_cmd(self, ctx: commands.Context):
        membro_id = self._membro_id_do_canal(ctx.channel.id)
        if membro_id is None:
            await ctx.send("⚠️ Esse comando só funciona dentro do canal de whitelist de um membro.", delete_after=8)
            return
        _, mensagem = await self.recusar_core(ctx.guild, membro_id, ctx.author, ctx.channel)
        await ctx.send(mensagem)

    @reprovar_whitelist_cmd.error
    async def reprovar_whitelist_cmd_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


    @app_commands.command(name="perfil-whitelist", description="[Staff] Vê o perfil/respostas da whitelist de um membro.")
    @app_commands.describe(membro="Membro cujo perfil de whitelist você quer ver")
    @app_commands.checks.has_role(CARGO_MEMBRO_EQUIPE_ID)
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
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Só quem tem o cargo de **Membro da Equipe** pode usar esse comando.", ephemeral=True
            )


    @app_commands.command(
        name="editar-whitelist",
        description="[Admin] Cria ou edita a whitelist de um membro na mão (rank, maior rank, nick, etc).",
    )
    @app_commands.describe(
        membro="Membro que vai ter a whitelist criada/editada",
        nick="Nick do jogador no Rocket League",
        rank="Rank atual no Rocket League",
        maior_rank="Maior rank já alcançado (peak)",
        peak_div="Divisão do maior rank alcançado",
        plataforma="Plataforma que o jogador usa",
    )
    @app_commands.choices(
        rank=[app_commands.Choice(name=r, value=r) for r in CARGO_RANKS.keys()],
        maior_rank=[app_commands.Choice(name=r, value=r) for r in PEAK_RANKS],
        peak_div=[app_commands.Choice(name=d, value=d) for d in DIVISOES],
        plataforma=[app_commands.Choice(name=p, value=p) for p in PLATAFORMAS],
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def editar_whitelist(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        nick: str | None = None,
        rank: app_commands.Choice[str] | None = None,
        maior_rank: app_commands.Choice[str] | None = None,
        peak_div: app_commands.Choice[str] | None = None,
        plataforma: app_commands.Choice[str] | None = None,
    ):
        """Comando pensado pra cadastrar/ajustar na mão a whitelist de jogadores
        que entraram antes do sistema existir (ou corrigir dados de quem já
        tem). Cria o registro como 'aprovada' se ainda não existir nenhum."""

        if not any([nick, rank, maior_rank, peak_div, plataforma]):
            await interaction.response.send_message(
                "⚠️ Informe pelo menos um campo pra alterar (nick, rank, maior rank, divisão ou plataforma).",
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
        embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
        embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
        embed.add_field(name="Maior rank", value=f"{r.get('peak_rank', '—')} ({r.get('peak_div', '—')})", inline=True)
        embed.add_field(name="Plataforma", value=r.get("plataforma", "—"), inline=True)
        embed.set_footer(text=f"Editado por {interaction.user}")

        if avisos:
            embed.add_field(name="⚠️ Avisos", value="\n".join(avisos), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @editar_whitelist.error
    async def editar_whitelist_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem usar este comando.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
