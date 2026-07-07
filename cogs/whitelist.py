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

# Cargo dado a todo mundo que termina a whitelist (vira "membro da equipe").
# Cargo normal — não está ligado a nenhuma checagem de comando admin do bot.
CARGO_MEMBRO_ID = 1523830313141272586

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

        # Passo especial: rank atual dá cargo na hora
        if self.step == "rank":
            await self.cog.aplicar_rank(interaction, membro, valor)
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
        await cog.finalizar(interaction)


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

    # ── Criação do canal privado ao entrar ──────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self.criar_canal_whitelist(member)

    async def criar_canal_whitelist(self, member: discord.Member) -> discord.TextChannel:
        guild = member.guild
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

    # ── Aplica o cargo de rank atual (remove outros ranks antes) ────
    async def aplicar_rank(self, interaction: discord.Interaction, membro: discord.Member, rank_nome: str):
        guild = interaction.guild
        cargo = guild.get_role(CARGO_RANKS.get(rank_nome, 0))
        if cargo is None:
            await interaction.response.send_message("⚠️ Não achei o cargo desse rank, chama a staff.")
            return
        cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS and r.id != cargo.id]
        try:
            if cargos_rank_atuais:
                await membro.remove_roles(*cargos_rank_atuais, reason="Whitelist — troca de rank")
            if cargo not in membro.roles:
                await membro.add_roles(cargo, reason="Whitelist — rank informado")
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ Não tenho permissão pra dar esse cargo, chama a staff.")
            return
        await interaction.response.send_message(f"✅ Cargo de rank **{rank_nome}** aplicado!")

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

    # ── Finalização ──────────────────────────────────────────────
    async def finalizar(self, interaction: discord.Interaction):
        membro = interaction.user
        guild = interaction.guild
        registro = self.dados.get(str(membro.id))
        if not registro:
            await interaction.response.send_message("⚠️ Não achei seus dados de whitelist. Chama a staff.", ephemeral=True)
            return

        cargo_membro = guild.get_role(CARGO_MEMBRO_ID)
        try:
            if cargo_membro and cargo_membro not in membro.roles:
                await membro.add_roles(cargo_membro, reason="Whitelist concluída")
        except discord.Forbidden:
            pass

        registro["status"] = "concluido"
        salvar("whitelist", self.dados)

        await interaction.response.send_message(
            "🎉 **Whitelist concluída!** Seja muito bem-vindo(a) à equipe — os canais do servidor já estão liberados pra você. 🚀"
        )

        # Trava o canal (só leitura pro membro, staff continua vendo tudo)
        try:
            await interaction.channel.set_permissions(membro, send_messages=False, view_channel=True)
        except discord.Forbidden:
            pass

        # Log pra staff
        if CANAL_LOG_WHITELIST_ID:
            canal_log = self.bot.get_channel(CANAL_LOG_WHITELIST_ID)
            if canal_log:
                r = registro["respostas"]
                embed = discord.Embed(title=f"📋 Whitelist concluída — {membro}", color=0x57F287)
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
