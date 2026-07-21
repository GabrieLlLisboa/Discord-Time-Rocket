import discord
from discord.ext import commands, tasks
import asyncio
import re
import time

from cogs.backup import ler, salvar
from cogs.players import CARGOS as PLAYER_CARGOS

# {"Ouro": id, "Platina": id, ...} — montado a partir dos cargos de rank já existentes
CARGO_RANKS = {c["nome"]: c["id"] for c in PLAYER_CARGOS if c["secao"] == "rank"}

# ─────────────────────────────────────────────
#  Cog: Whitelist
#  Arquivo: cogs/whitelist.py
#
#  Fluxo: membro entra -> só vê o canal "whitelist-<nick>" -> responde
#  uma sequência de perguntas -> no final recebe os cargos e o canal é
#  travado (fica só leitura, arquivado pra staff consultar se precisar).
# ─────────────────────────────────────────────

# ── CONFIGURAÇÕES (ajuste aqui se precisar) ─────────────────────────────────

# Categoria onde os canais de whitelist são criados. Deixe 0 que o bot
# procura (ou cria, se não existir) uma categoria chamada "🔒 Whitelist".
CATEGORIA_WHITELIST_ID = 0
NOME_CATEGORIA_WHITELIST = "🔒 Whitelist"

# Canal onde fica o log de cada whitelist concluída (nick, rank, plataforma, etc).
# 0 = desativado. Me passa o ID que eu preencho aqui.
CANAL_LOG_WHITELIST_ID = 1521897698419019907

# Canal onde fica o "quadro" de status de cada whitelist (pendente,
# em análise, aprovada, recusada). Deixe 0 que o bot cria/usa um canal
# chamado "status-whitelist" (fica visível pra todo mundo, só leitura).
STATUS_WHITELIST_CHANNEL_ID = 0
NOME_CANAL_STATUS = "status-whitelist"

STATUS_LABELS = {
    "pendente":    ("⏳ Pendente",   0xFEE75C),
    "visualizada": ("👀 Em análise", 0x5865F2),
    "aprovada":    ("✅ Aprovada",   0x57F287),
    "recusada":    ("❌ Recusada",   0xED4245),
}

# Cargo "membro da equipe" — NÃO é dado automaticamente no fim da whitelist
# (deixado aqui só de referência, caso você use em outro lugar).
CARGO_MEMBRO_ID = 1523830313141272586

# Cargo dado automaticamente (na hora, sem precisar de aprovação) pra quem
# escolhe "Inglês" na pergunta de idioma da whitelist.
CARGO_IDIOMA_INGLES_ID = 1525312330831892481

IDIOMAS = ["Português", "Inglês"]
IDIOMA_EMOJIS = {"Português": "🇧🇷", "Inglês": "🇬🇧"}

# Cargo que a pessoa recebe assim que entra no servidor — é ele que bloqueia
# a visão de todos os canais (configurado nas permissões dos canais como
# "negar" pra esse cargo). É removido automaticamente quando termina a whitelist.
CARGO_SEM_ACESSO_ID = 1521890714873757707

# Cargos de staff — quem tiver qualquer um desses, recebe automaticamente
# o cargo de "tag" de staff abaixo (isso é feito em cogs/staff_tag.py).
#
# Coach (1513356584946896946) e Editor de vídeo (1513240072139309317) têm
# "secao": "staff" em PLAYER_CARGOS (players.py), mas foram explicitamente
# excluídos daqui: quem tem só esses cargos NÃO recebe a tag de staff.
CARGOS_EXCLUIDOS_DA_TAG_STAFF = {
    1513240072139309317,  # Editor de vídeo
    1513356584946896946,  # Coach
}

STAFF_ROLE_IDS = ({c["id"] for c in PLAYER_CARGOS if c["secao"] == "staff"} | {
    1511894837790769204,  # Sub-Dono
    1523835085475020932,  # Diretor
    1523835045872275566,  # Gerente
    1523835010795176027,  # Moderador
    1523833330175442954,  # Suporte
    1523843469016043600,  # Tag de Staff
}) - CARGOS_EXCLUIDOS_DA_TAG_STAFF

# Cargos que podem ver os canais de whitelist (além do próprio membro).
# Só estes 3 — os demais cargos de staff (Gerente, Moderador, Suporte etc.)
# não têm acesso aos canais de whitelist.
CARGOS_QUE_VEEM_WHITELIST = {
    1511895253777649704,  # Dono do Clube
    1511894837790769204,  # Sub-Dono
    1523835085475020932,  # Diretor
}

RANK_IDS = set(CARGO_RANKS.values())

PLATAFORMAS = ["PC", "Xbox", "PlayStation", "Switch"]

PEAK_RANKS = [
    "Bronze", "Prata", "Ouro", "Platina",
    "Diamante", "Champion", "Grand Champion", "Supersonic Legend",
]
DIVISOES = ["Divisão 1", "Divisão 2", "Divisão 3"]

TEMPOS_JOGANDO = ["Menos de 1 ano", "1 a 2 anos", "2 a 4 anos", "Mais de 4 anos"]


def _slug(nome: str) -> str:
    nome = nome.lower().strip()
    nome = re.sub(r"[^a-z0-9\-]+", "-", nome)
    nome = re.sub(r"-+", "-", nome).strip("-")
    return nome or "jogador"


# ─────────────────────────────────────────────
#  Modal: nick no Rocket League
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
#  Modal: perguntas abertas (texto livre)
# ─────────────────────────────────────────────
class PerguntasAbertasModal(discord.ui.Modal, title="Whitelist — Perguntas"):
    motivo_entrada = discord.ui.TextInput(
        label="Por que você quer entrar no clube?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )
    reacao_regras = discord.ui.TextInput(
        label="Reação a membro quebrando regra/confusão?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )
    motivo_aceitar = discord.ui.TextInput(
        label="Por que deveríamos te aceitar?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, cog: "Whitelist"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        self.cog.salvar_resposta(membro.id, "motivo_entrada", self.motivo_entrada.value.strip())
        self.cog.salvar_resposta(membro.id, "reacao_regras", self.reacao_regras.value.strip())
        self.cog.salvar_resposta(membro.id, "motivo_aceitar", self.motivo_aceitar.value.strip())

        await interaction.response.send_message("✅ Respostas registradas!")
        await self.cog.enviar_pergunta(interaction.channel, membro, "duvidas")


# ─────────────────────────────────────────────
#  View: botão que abre o modal de perguntas abertas
# ─────────────────────────────────────────────
class AbrirPerguntasView(discord.ui.View):
    def __init__(self, cog: "Whitelist"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="📝 Responder Perguntas", style=discord.ButtonStyle.primary, custom_id="wl_perguntas_abertas")
    async def responder(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PerguntasAbertasModal(self.cog))


# ─────────────────────────────────────────────
#  View genérica de seleção (usada em várias perguntas)
# ─────────────────────────────────────────────
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

            # Conta com base nos membros reais do servidor (não só em quem já
            # respondeu a whitelist): quem tem o cargo de Inglês é falante de
            # Inglês, todo o resto (menos bots e o próprio membro) é considerado
            # falante de Português, já que é o idioma padrão do servidor.
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

        # Peak rank Supersonic Legend não tem divisão — pula direto
        if self.step == "peak_rank" and valor == "Supersonic Legend":
            self.cog.salvar_resposta(membro.id, "peak_div", "—")
            await self.cog.enviar_pergunta(interaction.channel, membro, "tempo")
            return

        if self.prox_step:
            await self.cog.enviar_pergunta(interaction.channel, membro, self.prox_step)


class EscolhaView(discord.ui.View):
    def __init__(self, cog: "Whitelist", step: str, opcoes: list[str], placeholder: str, prox_step: str | None, emojis: dict | None = None):
        super().__init__(timeout=None)
        self.add_item(EscolhaSelect(cog, step, opcoes, placeholder, prox_step, emojis))


# ─────────────────────────────────────────────
#  View inicial: botão "Começar Whitelist"
# ─────────────────────────────────────────────
class ComecarWhitelistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔥 Começar Whitelist", style=discord.ButtonStyle.success, custom_id="wl_comecar")
    async def comecar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        if interaction.channel.name != f"whitelist-{_slug(interaction.user.name)}" and \
           not interaction.channel.name.startswith("whitelist-"):
            await interaction.response.send_message("❌ Use isso no seu canal de whitelist.", ephemeral=True)
            return
        await interaction.response.send_modal(NickModal(cog))

    @discord.ui.button(label="🗑️ Cancelar/Fechar (staff)", style=discord.ButtonStyle.danger, custom_id="wl_cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cargos = {r.id for r in interaction.user.roles}
        if not (interaction.user.guild_permissions.administrator or cargos & CARGOS_QUE_VEEM_WHITELIST):
            await interaction.response.send_message("❌ Apenas staff pode fechar.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Fechando canal em 3 segundos...")
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Whitelist cancelada por {interaction.user}")


# ─────────────────────────────────────────────
#  View final: dúvidas + concluir
# ─────────────────────────────────────────────
class FinalizarWhitelistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Concluir Whitelist", style=discord.ButtonStyle.success, custom_id="wl_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.solicitar_aprovacao(interaction)


# ─────────────────────────────────────────────
#  View de revisão: só admin pode usar
# ─────────────────────────────────────────────
def _checar_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


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


# ─────────────────────────────────────────────
#  Cog principal
# ─────────────────────────────────────────────
class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("whitelist")  # {user_id_str: {"respostas": {...}, "canal_id":..., "status":...}}
        self.limpeza_canais.start()

    def cog_unload(self):
        self.limpeza_canais.cancel()

    @tasks.loop(minutes=1)
    async def limpeza_canais(self):
        await self.bot.wait_until_ready()
        agora = time.time()
        mudou = False
        for uid_str, registro in list(self.dados.items()):
            if registro.get("status") != "aprovada" or registro.get("canal_apagado"):
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

    # ── Persistência ─────────────────────────────────────────────
    def salvar_resposta(self, user_id: int, chave: str, valor: str):
        uid = str(user_id)
        registro = self.dados.setdefault(uid, {"respostas": {}, "status": "em_andamento"})
        registro["respostas"][chave] = valor
        salvar("whitelist", self.dados)

    # ── Categoria (cria se não existir) ─────────────────────────────
    async def get_categoria(self, guild: discord.Guild) -> discord.CategoryChannel:
        if CATEGORIA_WHITELIST_ID:
            cat = guild.get_channel(CATEGORIA_WHITELIST_ID)
            if isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name=NOME_CATEGORIA_WHITELIST)
        if cat is None:
            cat = await guild.create_category(NOME_CATEGORIA_WHITELIST, reason="Categoria de whitelist criada automaticamente")
        return cat

    # ── Canal de status (cria se não existir) ────────────────────────
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

    # ── Cria ou atualiza a linha da pessoa no quadro de status ───────
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

        if status in ("aprovada", "recusada"):
            decidido_por_id = registro.get("decidido_por_id")
            decidido_por_nome = registro.get("decidido_por_nome")
            if decidido_por_id:
                verbo = "Aprovado" if status == "aprovada" else "Recusado"
                embed.add_field(name="Responsável", value=f"{verbo} por <@{decidido_por_id}>", inline=False)
            elif decidido_por_nome:
                verbo = "Aprovado" if status == "aprovada" else "Recusado"
                embed.add_field(name="Responsável", value=f"{verbo} por **{decidido_por_nome}**", inline=False)

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

    # ── Criação do canal privado ao entrar ──────────────────────────
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

        self.dados[str(member.id)] = {"respostas": {}, "status": "em_andamento", "canal_id": canal.id}
        salvar("whitelist", self.dados)

        embed = discord.Embed(
            title="🔥 Bem-vindo(a)! Vamos fazer sua Whitelist",
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

    # Se a pessoa sair antes de terminar, limpa o canal
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        registro = self.dados.get(str(member.id))
        if not registro or registro.get("status") == "concluido":
            return
        canal_id = registro.get("canal_id")
        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal:
            try:
                await canal.delete(reason="Membro saiu antes de terminar a whitelist")
            except discord.HTTPException:
                pass

    # ── Dá o cargo de rank (remove outros ranks antes) — só na aprovação ──
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

    # ── Envia a pergunta correspondente ao passo ────────────────────
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
            view = EscolhaView(self, "ativo", ["Sim", "Não"], "Você vai ser ativo?", "perguntas_abertas")
            await canal.send("📈 **Você pretende ser um membro ativo na equipe?**", view=view)

        elif step == "perguntas_abertas":
            embed = discord.Embed(
                title="📝 Últimas perguntas",
                description=(
                    "Agora só faltam 3 perguntas rápidas com resposta em texto livre. "
                    "Clica no botão abaixo pra abrir o formulário:\n\n"
                    "• Por que você quer entrar no clube?\n"
                    "• Como você reagiria se visse um membro quebrando as regras ou causando confusão?\n"
                    "• Por que deveríamos aceitar você no clube?"
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

    # ── Pede aprovação (era o antigo "finalizar") ───────────────────
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

        # Trava o envio de mensagens pro membro enquanto aguarda análise
        try:
            await interaction.channel.set_permissions(membro, send_messages=False, view_channel=True)
        except discord.Forbidden:
            pass

        await self.atualizar_status_board(guild, membro.id)

        r = registro["respostas"]

        # Resumo completo pra staff, direto no canal privado da whitelist
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
        embed_resumo.add_field(name="Por que quer entrar?", value=r.get("motivo_entrada", "—"), inline=False)
        embed_resumo.add_field(name="Reação a quebra de regra", value=r.get("reacao_regras", "—"), inline=False)
        embed_resumo.add_field(name="Por que devemos aceitar?", value=r.get("motivo_aceitar", "—"), inline=False)
        embed_resumo.set_footer(text=f"ID: {membro.id}")
        await interaction.channel.send(embed=embed_resumo)

        # Painel de revisão pra staff, só dentro do próprio canal privado
        embed_revisao = discord.Embed(
            title="🔎 Whitelist aguardando revisão",
            description=f"Analisa as respostas de {membro.mention} e decide abaixo.\n(apenas **administradores**)",
            color=0xFEE75C,
        )
        await interaction.channel.send(embed=embed_revisao, view=RevisaoWhitelistView(membro.id))

        # Log completo pra staff
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
                embed.set_footer(text=f"ID: {membro.id}")
                await canal_log.send(embed=embed)

    # ── Admin marca como "em análise" ────────────────────────────────
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

    # ── Admin aprova ──────────────────────────────────────────────
    # Método "core": não depende de Interaction, então pode ser chamado
    # tanto pelo botão "✅ Aprovar" quanto pelo comando !aprovar-whitelist.
    # Retorna (ephemeral, mensagem) — `ephemeral` só é usado pelo botão
    # (Interaction); o comando de texto sempre manda a mensagem normal.
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

        # Trava a whitelist JÁ AQUI, antes de qualquer `await`. Como o bot
        # roda tudo num único loop assíncrono, nada mais executa entre uma
        # linha e outra até a primeira pausa (await) — então, se dois
        # admins clicarem/digitarem quase ao mesmo tempo, só o primeiro
        # passa por essa checagem; o segundo já vai cair no bloco acima.
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
            f"{membro.mention if membro else ''} os canais do servidor já estão liberados. Bem-vindo(a)! 🔥{aviso_rank}\n"
            f"*(este canal vai ser apagado automaticamente em 10 minutos)*"
        )

        # Tira a visão do canal de whitelist pro membro (ele não precisa mais dele)
        if membro:
            try:
                await canal.set_permissions(membro, overwrite=None)
            except discord.Forbidden:
                pass

        # Agenda a exclusão do canal em 10 minutos (sobrevive a restart do bot)
        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        return False, mensagem

    # ── Admin recusa -> expulsa o membro automaticamente ─────────────
    # Sempre que a whitelist é reprovada, o membro é removido do servidor
    # (banimento não, só kick — ele pode entrar de novo e tentar outra vez
    # do zero se quiser).
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

        # Mesma trava imediata explicada em aprovar_core()
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

        # Agenda a exclusão do canal em 10 minutos, igual à aprovação —
        # como o membro foi expulso, não faz sentido reabrir o processo.
        registro["deletar_em"] = time.time() + 600
        registro["canal_apagado"] = False
        salvar("whitelist", self.dados)

        mensagem = (
            f"❌ **Whitelist recusada por {autor.mention}.** "
            f"{membro.mention if membro else 'O membro'} foi removido do servidor automaticamente.{aviso_kick}\n"
            f"*(este canal vai ser apagado automaticamente em 10 minutos)*"
        )
        return False, mensagem

    # ── Acha de qual membro é o canal de whitelist atual (pelos comandos) ──
    def _membro_id_do_canal(self, canal_id: int) -> int | None:
        for membro_id_str, registro in self.dados.items():
            if registro.get("canal_id") == canal_id:
                return int(membro_id_str)
        return None

    # ── Comando manual pra staff criar/recriar o canal de alguém ────
    @commands.command(name="whitelist")
    @commands.has_permissions(administrator=True)
    async def whitelist_manual(self, ctx: commands.Context, membro: discord.Member):
        await ctx.message.delete()
        canal = await self.criar_canal_whitelist(membro)
        await ctx.send(f"✅ Canal de whitelist pronto: {canal.mention}", delete_after=6)

    @whitelist_manual.error
    async def whitelist_manual_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Não achei esse membro.", delete_after=5)

    # ── Comandos de texto: aprovar/reprovar a whitelist do canal atual ──
    # Uso: dentro do canal "whitelist-<nick>" da pessoa, digitar
    # !aprovar-whitelist ou !reprovar-whitelist. Fazem exatamente a mesma
    # coisa que os botões "✅ Aprovar" / "❌ Recusar" no board de revisão.
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
