import discord
from discord.ext import commands
import asyncio
import re

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

# Canal onde fica o log de cada whitelist concluída (nick, rank, idade, etc).
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

# Cargo que a pessoa recebe assim que entra no servidor — é ele que bloqueia
# a visão de todos os canais (configurado nas permissões dos canais como
# "negar" pra esse cargo). É removido automaticamente quando termina a whitelist.
CARGO_SEM_ACESSO_ID = 1521890714873757707

# Cargos de staff — quem tiver qualquer um desses, recebe automaticamente
# o cargo de "tag" de staff abaixo (isso é feito em cogs/staff_tag.py).
STAFF_ROLE_IDS = {c["id"] for c in PLAYER_CARGOS if c["secao"] == "staff"} | {
    1511894837790769204,  # Sub-Dono  (⚠️ mesmo ID do cargo "Administrador" — confere se não é engano)
    1523835085475020932,  # Diretor
    1523835045872275566,  # Gerente
    1523835010795176027,  # Moderador
    1523833330175442954,  # Suporte
}

# Cargos que sempre podem ver os canais de whitelist (além do próprio membro)
CARGOS_QUE_VEEM_WHITELIST = STAFF_ROLE_IDS

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
        await self.cog.enviar_pergunta(interaction.channel, membro, "rank")


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

        if self.step == "rank":
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

    @discord.ui.button(label="🚀 Começar Whitelist", style=discord.ButtonStyle.success, custom_id="wl_comecar")
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
        await cog.aprovar(interaction, self.membro_id)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger, custom_id="wl_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _checar_admin(interaction):
            await interaction.response.send_message("❌ Só administradores podem revisar whitelists.", ephemeral=True)
            return
        cog: Whitelist = interaction.client.get_cog("Whitelist")
        await cog.recusar(interaction, self.membro_id)


# ─────────────────────────────────────────────
#  Cog principal
# ─────────────────────────────────────────────
class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("whitelist")  # {user_id_str: {"respostas": {...}, "canal_id":..., "status":...}}

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
        if step == "rank":
            view = EscolhaView(self, "rank", list(CARGO_RANKS.keys()), "Escolha seu rank atual...", "idade")
            await canal.send("🎮 **Qual o seu rank atual no Rocket League?**", view=view)

        elif step == "idade":
            view = EscolhaView(self, "idade", ["Menos de 13", "Maior que 13", "Maior que 18"], "Escolha sua idade...", "plataforma")
            await canal.send("🎂 **Quantos anos você tem?**\n*(seja sincero, isso não muda quase nada)*", view=view)

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
            view = EscolhaView(self, "ativo", ["Sim", "Não"], "Você vai ser ativo?", "duvidas")
            await canal.send("📈 **Você pretende ser um membro ativo na equipe?**", view=view)

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
                r = registro["respostas"]
                embed = discord.Embed(title=f"📋 Whitelist enviada para análise — {membro}", color=0xFEE75C)
                embed.set_thumbnail(url=membro.display_avatar.url)
                embed.add_field(name="Nick RL", value=r.get("nick", "—"), inline=True)
                embed.add_field(name="Rank atual", value=r.get("rank", "—"), inline=True)
                embed.add_field(name="Idade", value=r.get("idade", "—"), inline=True)
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
        salvar("whitelist", self.dados)
        await self.atualizar_status_board(interaction.guild, membro_id)
        await interaction.response.send_message(f"👀 Marcada como em análise por {interaction.user.mention}.")

    # ── Admin aprova ──────────────────────────────────────────────
    async def aprovar(self, interaction: discord.Interaction, membro_id: int):
        guild = interaction.guild
        registro = self.dados.get(str(membro_id))
        if not registro:
            await interaction.response.send_message("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return

        membro = guild.get_member(membro_id)
        cargo_sem_acesso = guild.get_role(CARGO_SEM_ACESSO_ID)
        if membro and cargo_sem_acesso and cargo_sem_acesso in membro.roles:
            try:
                await membro.remove_roles(cargo_sem_acesso, reason=f"Whitelist aprovada por {interaction.user}")
            except discord.Forbidden:
                pass

        aviso_rank = ""
        rank_nome = registro["respostas"].get("rank")
        if membro and rank_nome:
            erro = await self.dar_cargo_rank(guild, membro, rank_nome)
            if erro:
                aviso_rank = f"\n{erro}"

        registro["status"] = "aprovada"
        salvar("whitelist", self.dados)
        await self.atualizar_status_board(guild, membro_id)

        await interaction.response.send_message(
            f"✅ **Whitelist aprovada por {interaction.user.mention}!** "
            f"{membro.mention if membro else ''} os canais do servidor já estão liberados. Bem-vindo(a)! 🚀{aviso_rank}"
        )

    # ── Admin recusa -> reinicia a whitelist da pessoa ───────────────
    async def recusar(self, interaction: discord.Interaction, membro_id: int):
        guild = interaction.guild
        registro = self.dados.get(str(membro_id))
        if not registro:
            await interaction.response.send_message("⚠️ Não achei os dados dessa whitelist.", ephemeral=True)
            return

        membro = guild.get_member(membro_id)

        registro["status"] = "recusada"
        salvar("whitelist", self.dados)
        await self.atualizar_status_board(guild, membro_id)

        await interaction.response.send_message(
            f"❌ **Whitelist recusada por {interaction.user.mention}.** Vamos reiniciar o processo abaixo."
        )

        # Reabre o canal e reinicia do zero
        registro["respostas"] = {}
        registro["status"] = "em_andamento"
        salvar("whitelist", self.dados)

        if membro:
            try:
                await interaction.channel.set_permissions(membro, view_channel=True, send_messages=True, read_message_history=True)
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            title="🔁 Vamos tentar de novo!",
            description=(
                f"{membro.mention if membro else ''} sua whitelist foi recusada, mas sem problemas — "
                f"clica no botão abaixo e vamos refazer as perguntas. 👇"
            ),
            color=0x57F287,
        )
        await interaction.channel.send(embed=embed, view=ComecarWhitelistView())

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
