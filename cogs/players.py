import discord
from discord.ext import commands, tasks
import asyncio
import uuid

from cogs.backup import ler, salvar
from cogs.json_store import ler_json, salvar_json

CANAIS_PAINEL_RANK_PATH = "data/canais_painel_rank.json"

# ─────────────────────────────────────────────
#  Cog: Lista de Jogadores
#  Arquivo: cogs/players.py
# ─────────────────────────────────────────────

JOGADORES_CHANNEL_ID = 1529233959744049172

# Canal onde caem as pendências de troca de rank (subida/descida),
# pra staff analisar a comprovação e aprovar ou recusar — usado pelo
# painel enviado com !setup-rank.
PEDIDOS_RANK_CHANNEL_ID = 1529234086420418653

# Dono do Clube não é mais um cargo do Discord — é uma pessoa específica,
# identificada pelo ID de usuário abaixo (mesmo ID usado como autorizado
# em cogs/conversar.py, cogs/atividade.py e cogs/auto_update.py).
DONO_CLUBE_USER_ID = 1487452210605588592

CARGOS = [
    {"nome": "Admin",              "id": 1529150684296122438, "emoji": "🥈", "secao": "staff"},
    {"nome": "Coach",              "id": 1529160458769006804, "emoji": "📋", "secao": "staff"},
    {"nome": "Editor de vídeo",    "id": 1513240072139309317, "emoji": "🎬", "secao": "staff"},
    {"nome": "Super Sonic Legend", "id": 1529152122942390366, "emoji": "🌌", "secao": "rank"},
    {"nome": "Grand Champion",     "id": 1529152259630305402, "emoji": "👑", "secao": "rank"},
    {"nome": "Champion",           "id": 1529152654629142679, "emoji": "🏅", "secao": "rank"},
    {"nome": "Diamante",           "id": 1529153925486215350, "emoji": "💎", "secao": "rank"},
    {"nome": "Platina",            "id": 1529154068314849450, "emoji": "🪙", "secao": "rank"},
]

IDS_MONITORADOS  = {c["id"] for c in CARGOS}
CARGO_MAP        = {c["id"]: c for c in CARGOS}
RANK_IDS         = {c["id"] for c in CARGOS if c["secao"] == "rank"}
STAFF_IDS        = {c["id"] for c in CARGOS if c["secao"] == "staff"}
CARGOS_RANK      = [c for c in CARGOS if c["secao"] == "rank"]  # usados no painel !setup-rank

def _membros_do_cargo(guild: discord.Guild, cargo_id: int) -> list:
    """Membros de um cargo, já filtrando bots."""
    cargo = guild.get_role(cargo_id)
    if cargo is None:
        return []
    return [m for m in cargo.members if not m.bot]


def build_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🔥  Ignition RL — Esquadrão de Rocket League",
        color=0xFF5A1F,
    )

    dono = guild.get_member(DONO_CLUBE_USER_ID)
    embed.add_field(
        name="👑  **Dono do Clube**  `(1)`" if dono else "👑  **Dono do Clube**  `(0)`",
        value=f"  ▸  {dono.display_name}\n\u200b" if dono else "  *— não encontrado no servidor —*\n\u200b",
        inline=False,
    )

    for cargo_info in CARGOS:
        membros = sorted(
            _membros_do_cargo(guild, cargo_info["id"]),
            key=lambda m: m.display_name.lower()
        )

        if membros:
            lista = "\n".join(f"  ▸  {m.display_name}" for m in membros)
        else:
            lista = "  *— nenhum jogador —*"

        embed.add_field(
            name=f"{cargo_info['emoji']}  **{cargo_info['nome']}**  `({len(membros)})`",
            value=f"{lista}\n\u200b",
            inline=False,
        )

    total_membros = sum(1 for m in guild.members if not m.bot)
    embed.set_footer(text=f"🔥 {total_membros} membros na squad  •  Atualiza a cada 5 min")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _achar_rank_por_nome(nome: str) -> dict | None:
    """Acha o cargo de rank pelo nome digitado no modal (case-insensitive,
    ignora espaços nas pontas). Retorna None se não encontrar."""
    alvo = nome.strip().lower()
    for c in CARGOS_RANK:
        if c["nome"].lower() == alvo:
            return c
    return None


def _rank_atual(membro: discord.Member) -> dict | None:
    cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS]
    return CARGO_MAP.get(cargos_rank_atuais[0].id) if cargos_rank_atuais else None


# ─────────────────────────────────────────────
#  Modal: pedido de troca de rank (subida ou descida)
#  Preenchido pelo próprio jogador, direto pelo botão do painel.
# ─────────────────────────────────────────────
class SolicitarRankModal(discord.ui.Modal):
    novo_rank = discord.ui.TextInput(
        label="Qual o novo rank?",
        placeholder="Ex: Diamante, Champion, Grand Champion...",
        max_length=40,
        required=True,
    )

    def __init__(self, tipo: str):
        titulo = "⬆️ Solicitar subida de rank" if tipo == "subir" else "⬇️ Solicitar descida de rank"
        super().__init__(title=titulo)
        self.tipo = tipo

    async def on_submit(self, interaction: discord.Interaction):
        membro = interaction.user
        novo_info = _achar_rank_por_nome(self.novo_rank.value)
        if novo_info is None:
            opcoes = ", ".join(c["nome"] for c in CARGOS_RANK)
            await interaction.response.send_message(
                f"❌ Não achei o rank **{self.novo_rank.value}**. Digite exatamente um destes: {opcoes}",
                ephemeral=True,
            )
            return

        canal_staff = interaction.client.get_channel(PEDIDOS_RANK_CHANNEL_ID)
        if canal_staff is None:
            await interaction.response.send_message(
                "⚠️ Não achei o canal de pendências de rank. Chama a staff diretamente.",
                ephemeral=True,
            )
            return

        # O modal do Discord só aceita texto — pra anexar print/vídeo, a
        # pessoa manda como uma mensagem normal aqui no canal logo em
        # seguida, e o bot pega o anexo (ou o link, se ela colar um).
        #
        # IMPORTANTE: marca a sessão como "aguardando" ANTES de mandar a
        # mensagem pedindo a comprovação. Se fizer isso depois, existe uma
        # corrida: o await de enviar a mensagem leva um tempinho, e se a
        # pessoa for rápida o suficiente pra já responder, o on_message
        # apaga a mensagem dela achando que é conversa fora do fluxo.
        cog: "Players" = interaction.client.get_cog("Players")
        sessao = (interaction.channel.id, membro.id)
        cog.aguardando_comprovacao.add(sessao)

        await interaction.response.send_message(
            f"📎 Beleza! Agora manda **uma mensagem aqui neste canal** com a comprovação do rank "
            f"**{novo_info['nome']}** — pode **anexar o print/vídeo** ou colar um link. Você tem 5 minutos.",
            ephemeral=True,
        )

        def check(m: discord.Message) -> bool:
            return m.author.id == membro.id and m.channel.id == interaction.channel.id

        try:
            msg_comprovacao = await interaction.client.wait_for("message", check=check, timeout=300)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏰ Tempo esgotado esperando a comprovação. Clica no botão de novo pra tentar outra vez.",
                ephemeral=True,
            )
            return
        finally:
            cog.aguardando_comprovacao.discard(sessao)

        anexos = [a.url for a in msg_comprovacao.attachments]
        texto = msg_comprovacao.content.strip()

        if not anexos and not texto:
            await interaction.followup.send(
                "❌ Não veio nenhum anexo nem link nessa mensagem. Clica no botão de novo pra tentar de novo.",
                ephemeral=True,
            )
            try:
                await msg_comprovacao.delete()
            except discord.HTTPException:
                pass
            return

        # Baixa os anexos JÁ, antes de qualquer outra coisa — quanto mais
        # cedo, menor a chance de outro processo (automod, a própria pessoa
        # apagando, etc.) apagar a mensagem antes do bot conseguir ler o
        # arquivo. Se mesmo assim falhar, a pendência ainda é mandada só
        # com o link/texto, em vez de sumir tudo em silêncio.
        try:
            arquivos = [await a.to_file() for a in msg_comprovacao.attachments]
        except (discord.NotFound, discord.HTTPException):
            arquivos = []

        atual_info = _rank_atual(membro)
        pedido_id = uuid.uuid4().hex[:10]

        cor = 0x57F287 if self.tipo == "subir" else 0xED4245
        emoji_tipo = "⬆️" if self.tipo == "subir" else "⬇️"
        embed = discord.Embed(
            title=f"{emoji_tipo} Pedido de {'subida' if self.tipo == 'subir' else 'descida'} de rank",
            description=f"{membro.mention} está solicitando uma alteração de rank.",
            color=cor,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(
            name="Rank atual",
            value=f"{atual_info['emoji']} {atual_info['nome']}" if atual_info else "— nenhum —",
            inline=True,
        )
        embed.add_field(name="Novo rank solicitado", value=f"{novo_info['emoji']} {novo_info['nome']}", inline=True)
        embed.add_field(name="Comprovação", value=texto if texto else "*(ver anexo abaixo)*", inline=False)
        if anexos and not arquivos:
            # Não conseguiu baixar o anexo original — pelo menos deixa o
            # link registrado, pra staff não ficar sem nada.
            embed.add_field(name="Anexo(s) (link original)", value="\n".join(anexos), inline=False)
        elif anexos:
            # Se for imagem, já mostra ela direto na embed; se não for
            # (vídeo, etc.), o arquivo ainda vai anexado de verdade na mensagem.
            primeiro = anexos[0].lower()
            if primeiro.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                embed.set_image(url=f"attachment://{arquivos[0].filename}")
        embed.set_footer(text=f"ID do jogador: {membro.id} • Pedido {pedido_id}")

        view = PendenciaRankView(pedido_id)
        msg = await canal_staff.send(
            content=f"📋 Novo pedido de rank — {membro.mention}",
            embed=embed,
            view=view,
            files=arquivos,
        )

        cog.pedidos[pedido_id] = {
            "solicitante_id": membro.id,
            "tipo": self.tipo,
            "rank_atual_id": atual_info["id"] if atual_info else None,
            "novo_rank_id": novo_info["id"],
            "comprovacao": texto or "(anexo)",
            "anexos": anexos,
            "status": "pendente",
            "canal_id": canal_staff.id,
            "msg_id": msg.id,
        }
        salvar("pedidos_rank", cog.pedidos)

        try:
            await msg_comprovacao.delete()
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            f"📨 Pedido enviado! A staff vai analisar sua comprovação em {canal_staff.mention} e te avisar por lá assim que decidir.",
            ephemeral=True,
        )


# ─────────────────────────────────────────────
#  Modal: motivo da recusa de um pedido de rank
# ─────────────────────────────────────────────
class RecusaPedidoRankModal(discord.ui.Modal, title="Recusar pedido de rank"):
    motivo = discord.ui.TextInput(
        label="Motivo da recusa",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
        placeholder="Explique por que esse pedido está sendo recusado",
    )

    def __init__(self, pedido_id: str, view: "PendenciaRankView"):
        super().__init__()
        self.pedido_id = pedido_id
        self.view_pendencia = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_pendencia._recusar_core(interaction, self.pedido_id, self.motivo.value.strip())


# ─────────────────────────────────────────────
#  View: aprovar/recusar pedido de rank (mandada no canal de staff)
# ─────────────────────────────────────────────
class PendenciaRankView(discord.ui.View):
    def __init__(self, pedido_id: str):
        super().__init__(timeout=None)
        self.pedido_id = pedido_id
        self.aprovar.custom_id = f"rankpend_aprovar:{pedido_id}"
        self.recusar.custom_id = f"rankpend_recusar:{pedido_id}"

    def _checar_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._checar_admin(interaction):
            await interaction.response.send_message("❌ Apenas **Administradores** podem decidir pedidos de rank.", ephemeral=True)
            return

        cog: "Players" = interaction.client.get_cog("Players")
        pedido = cog.pedidos.get(self.pedido_id)
        if pedido is None:
            await interaction.response.send_message("⚠️ Não achei os dados desse pedido.", ephemeral=True)
            return
        if pedido["status"] != "pendente":
            await interaction.response.send_message(f"⚠️ Esse pedido já foi **{pedido['status']}**.", ephemeral=True)
            return

        await interaction.response.defer()

        guild = interaction.guild
        membro = guild.get_member(pedido["solicitante_id"])
        novo_info = CARGO_MAP[pedido["novo_rank_id"]]
        novo_cargo = guild.get_role(pedido["novo_rank_id"])

        if membro is None or novo_cargo is None:
            await interaction.followup.send("⚠️ Jogador ou cargo não encontrado no servidor.", ephemeral=True)
            return

        cargos_rank_atuais = [r for r in membro.roles if r.id in RANK_IDS]
        try:
            if cargos_rank_atuais:
                await membro.remove_roles(*cargos_rank_atuais, reason=f"Pedido de rank aprovado por {interaction.user}")
            await membro.add_roles(novo_cargo, reason=f"Pedido de rank aprovado por {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão pra alterar os cargos desse jogador.", ephemeral=True)
            return

        pedido["status"] = "aprovado"
        pedido["decidido_por_id"] = interaction.user.id
        salvar("pedidos_rank", cog.pedidos)

        # Anúncio no canal de jogadores + atualiza a lista
        channel = interaction.client.get_channel(JOGADORES_CHANNEL_ID)
        if channel is not None:
            atual_info = CARGO_MAP.get(pedido["rank_atual_id"]) if pedido.get("rank_atual_id") else None
            if pedido["tipo"] == "subir":
                msg = (
                    f"⬆️ **{membro.display_name}** upou do rank {atual_info['emoji']} **{atual_info['nome']}** "
                    f"para o rank {novo_info['emoji']} **{novo_info['nome']}**!"
                    if atual_info else
                    f"🎉 **{membro.display_name}** entrou no clube com o rank {novo_info['emoji']} **{novo_info['nome']}**!"
                )
            else:
                msg = (
                    f"⬇️ **{membro.display_name}** desceu do rank {atual_info['emoji']} **{atual_info['nome']}** "
                    f"para o rank {novo_info['emoji']} **{novo_info['nome']}**."
                    if atual_info else
                    f"📉 **{membro.display_name}** entrou no rank {novo_info['emoji']} **{novo_info['nome']}**."
                )
            notif = await channel.send(msg)
            await notif.delete(delay=300)
            if cog:
                await cog._editar_ou_criar(channel)

        embed = interaction.message.embeds[0]
        embed.add_field(name="Decisão", value=f"✅ Aprovado por {interaction.user.mention}", inline=False)
        embed.color = 0x57F287
        self.aprovar.disabled = True
        self.recusar.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        await interaction.followup.send(f"✅ Pedido aprovado! Rank de {membro.mention} atualizado pra {novo_info['emoji']} **{novo_info['nome']}**.")

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._checar_admin(interaction):
            await interaction.response.send_message("❌ Apenas **Administradores** podem decidir pedidos de rank.", ephemeral=True)
            return

        cog: "Players" = interaction.client.get_cog("Players")
        pedido = cog.pedidos.get(self.pedido_id)
        if pedido is None:
            await interaction.response.send_message("⚠️ Não achei os dados desse pedido.", ephemeral=True)
            return
        if pedido["status"] != "pendente":
            await interaction.response.send_message(f"⚠️ Esse pedido já foi **{pedido['status']}**.", ephemeral=True)
            return

        await interaction.response.send_modal(RecusaPedidoRankModal(self.pedido_id, self))

    async def _recusar_core(self, interaction: discord.Interaction, pedido_id: str, motivo: str):
        cog: "Players" = interaction.client.get_cog("Players")
        pedido = cog.pedidos.get(pedido_id)
        if pedido is None or pedido["status"] != "pendente":
            await interaction.response.send_message("⚠️ Esse pedido não existe mais ou já foi decidido.", ephemeral=True)
            return

        pedido["status"] = "recusado"
        pedido["decidido_por_id"] = interaction.user.id
        pedido["motivo_recusa"] = motivo
        salvar("pedidos_rank", cog.pedidos)

        embed = interaction.message.embeds[0]
        embed.add_field(name="Decisão", value=f"❌ Recusado por {interaction.user.mention}\n**Motivo:** {motivo}", inline=False)
        embed.color = 0xED4245
        self.aprovar.disabled = True
        self.recusar.disabled = True
        await interaction.message.edit(embed=embed, view=self)

        await interaction.response.send_message(f"❌ Pedido recusado.\n**Motivo:** {motivo}")


# ─────────────────────────────────────────────
#  View: painel fixo enviado pelo comando !setup-rank
#  Qualquer jogador pode clicar — é ele quem solicita a troca.
# ─────────────────────────────────────────────
class PainelSolicitarRankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Subir de Rank", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="players_rank_solicitar_subir")
    async def subir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SolicitarRankModal("subir"))

    @discord.ui.button(label="Descer de Rank", emoji="⬇️", style=discord.ButtonStyle.danger, custom_id="players_rank_solicitar_descer")
    async def descer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SolicitarRankModal("descer"))


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot        = bot
        self.message_id = None
        self.pedidos    = ler("pedidos_rank")  # {pedido_id: {...}}
        self.bot.add_view(PainelSolicitarRankView())  # mantém os botões funcionando após restart

        # Canais onde o painel !setup-rank foi enviado — nesses canais só
        # pode rolar o fluxo de pedido de rank, o resto é apagado (ver on_message).
        self.canais_painel_rank: set[int] = set(ler_json(CANAIS_PAINEL_RANK_PATH, []))

        # (channel_id, user_id) de quem já clicou no botão, preencheu o
        # modal e está esperando mandar a comprovação — enquanto estiver
        # aqui, a mensagem dela não é apagada pelo on_message (quem processa
        # e apaga é o próprio fluxo do modal, depois de coletar a imagem).
        self.aguardando_comprovacao: set[tuple[int, int]] = set()

        # Reregistra os botões Aprovar/Recusar dos pedidos ainda pendentes,
        # senão eles param de funcionar depois de um restart do bot.
        for pedido_id, pedido in self.pedidos.items():
            if pedido.get("status") == "pendente":
                self.bot.add_view(PendenciaRankView(pedido_id))

        self.atualizar_lista.start()

    def cog_unload(self):
        self.atualizar_lista.cancel()

    # Mantém o(s) canal(is) do painel de rank limpos: qualquer mensagem que
    # não seja a comprovação de alguém que já clicou no botão e preencheu o
    # modal é apagada na hora (a mensagem de comprovação em si é apagada
    # depois, pelo próprio fluxo do modal, já com a imagem coletada).
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in self.canais_painel_rank:
            return
        if (message.channel.id, message.author.id) in self.aguardando_comprovacao:
            return  # é a comprovação esperada — o fluxo do modal cuida dela
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Ranks não são mais detectados automaticamente por diff de cargo
        # (isso causava mensagem errada às vezes). Agora eles só são
        # anunciados via painel `!setup-rank`. Aqui só sobra a staff.
        cargos_antes  = {r.id for r in before.roles}
        cargos_depois = {r.id for r in after.roles}
        ganhou  = (cargos_depois - cargos_antes) & STAFF_IDS
        perdeu  = (cargos_antes - cargos_depois) & STAFF_IDS
        if not ganhou and not perdeu:
            return
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        if channel is None:
            return

        linhas = []
        for cid in ganhou:
            info = CARGO_MAP[cid]
            linhas.append(f"📈 **{after.display_name}** subiu para {info['emoji']} **{info['nome']}**!")
        for cid in perdeu:
            info = CARGO_MAP[cid]
            linhas.append(f"📉 **{after.display_name}** saiu de {info['emoji']} **{info['nome']}**.")

        if linhas:
            notif = await channel.send("\n".join(linhas))
            await self._editar_ou_criar(channel)
            await notif.delete(delay=300)

    @tasks.loop(minutes=5)
    async def atualizar_lista(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        if channel is None:
            print(f"[PLAYERS] ⚠️  Canal {JOGADORES_CHANNEL_ID} não encontrado.")
            return
        try:
            await self._editar_ou_criar(channel)
        except Exception as e:
            # Uma falha pontual (ex: mensagem apagada na hora errada, erro de
            # rede do Discord) não pode derrubar essa atualização periódica
            # pro resto da vida do processo.
            print(f"[PLAYERS] ⚠️ Erro ao atualizar lista de jogadores: {e}")

    @atualizar_lista.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()

    async def _editar_ou_criar(self, channel: discord.TextChannel):
        embed = build_embed(channel.guild)
        if self.message_id:
            try:
                msg = await channel.fetch_message(self.message_id)
                await msg.edit(embed=embed)
                print("[PLAYERS] 🔄 Lista atualizada.")
                return
            except discord.NotFound:
                self.message_id = None
        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.embeds:
                if "Ignition" in (msg.embeds[0].title or ""):
                    self.message_id = msg.id
                    await msg.edit(embed=embed)
                    return
        nova = await channel.send(embed=embed)
        self.message_id = nova.id
        print(f"[PLAYERS] ✅ Lista criada no canal #{channel.name}.")

    @commands.command(name="atualizarjogadores")
    @commands.has_permissions(administrator=True)
    async def forcar_atualizacao(self, ctx: commands.Context):
        await ctx.message.delete()
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        await self._editar_ou_criar(channel)
        await ctx.send("✅ Lista de jogadores atualizada!", delete_after=4)

    @commands.command(name="setup-rank")
    @commands.has_permissions(administrator=True)
    async def setup_rank(self, ctx: commands.Context):
        """Envia o painel de solicitação de troca de rank (Subir/Descer) neste canal."""
        embed = discord.Embed(
            title="🎮 Painel de Troca de Rank",
            description=(
                "Subiu ou desceu de rank? Clica no botão certo abaixo!\n\n"
                "Você vai informar o **novo rank** e depois mandar a **comprovação** "
                "(print/vídeo anexado ou link). "
                f"O pedido cai como pendência em <#{PEDIDOS_RANK_CHANNEL_ID}> pra staff analisar e aprovar. "
                "Assim que for aprovado, seu cargo é trocado automaticamente.\n\n"
                "⚠️ **Este canal é só pra isso** — qualquer outra mensagem é apagada automaticamente."
            ),
            color=0xFF5A1F,
        )
        await ctx.send(embed=embed, view=PainelSolicitarRankView())

        # Marca este canal como "canal do painel" — o on_message vai manter
        # ele limpo, só deixando passar a comprovação de quem clicou no botão.
        self.canais_painel_rank.add(ctx.channel.id)
        salvar_json(CANAIS_PAINEL_RANK_PATH, list(self.canais_painel_rank))

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @setup_rank.error
    async def setup_rank_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)

    @forcar_atualizacao.error
    async def forcar_atualizacao_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
