import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────
#  Cog: Lista de Jogadores
#  Arquivo: cogs/players.py
# ─────────────────────────────────────────────

JOGADORES_CHANNEL_ID = 1514775408124367149

CARGOS = [
    {"nome": "Dono do Clube",      "id": 1511895253777649704, "emoji": "👑", "secao": "staff"},
    {"nome": "Sub-Dono",           "id": 1511894837790769204, "emoji": "🥈", "secao": "staff"},
    {"nome": "Diretor",            "id": 1523835085475020932, "emoji": "🎖️", "secao": "staff"},
    {"nome": "Gerente",            "id": 1523835045872275566, "emoji": "🗂️", "secao": "staff"},
    {"nome": "Moderador",          "id": 1523835010795176027, "emoji": "🔨", "secao": "staff"},
    {"nome": "Suporte",            "id": 1523833330175442954, "emoji": "🎧", "secao": "staff"},
    {"nome": "Coach",              "id": 1513356584946896946, "emoji": "📋", "secao": "staff"},
    {"nome": "Editor de vídeo",    "id": 1513240072139309317, "emoji": "🎬", "secao": "staff"},
    {"nome": "Super Sonic Legend", "id": 1514772134327488642, "emoji": "🌌", "secao": "rank"},
    {"nome": "Grand Champion",     "id": 1513343857125752992, "emoji": "👑", "secao": "rank"},
    {"nome": "Champion",           "id": 1512304793534861313, "emoji": "🏅", "secao": "rank"},
    {"nome": "Diamante",           "id": 1512305401075466320, "emoji": "💎", "secao": "rank"},
    {"nome": "Platina",            "id": 1512305547544625273, "emoji": "🪙", "secao": "rank"},
    {"nome": "Ouro",               "id": 1512571913849933956, "emoji": "🥇", "secao": "rank"},
]

IDS_MONITORADOS  = {c["id"] for c in CARGOS}
CARGO_MAP        = {c["id"]: c for c in CARGOS}
RANK_IDS         = {c["id"] for c in CARGOS if c["secao"] == "rank"}
STAFF_IDS        = {c["id"] for c in CARGOS if c["secao"] == "staff"}
CARGOS_RANK      = [c for c in CARGOS if c["secao"] == "rank"]  # usados no painel !setup-rank

# Quem tiver qualquer um desses cargos não aparece na lista de jogadores
IDS_OCULTOS = {1521890714873757707, 1514782308031533116}


def _esta_oculto(membro: discord.Member) -> bool:
    return bool(IDS_OCULTOS & {r.id for r in membro.roles})


def _membros_do_cargo(guild: discord.Guild, cargo_id: int) -> list:
    """Membros de um cargo, já filtrando bots e membros ocultos."""
    cargo = guild.get_role(cargo_id)
    if cargo is None:
        return []
    return [m for m in cargo.members if not m.bot and not _esta_oculto(m)]


def build_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🚀  TryHarders RL — Time de Rocket League",
        color=0xD4A843,
    )

    embed.add_field(name="\u200b", value="```╔══════════  🏢  STAFF  ══════════╗```", inline=False)

    for cargo_info in CARGOS:
        if cargo_info["secao"] != "staff":
            continue

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

    total_membros = sum(1 for m in guild.members if not m.bot and not _esta_oculto(m))
    embed.set_footer(text=f"⚡ {total_membros} membros no clube  •  Atualiza a cada 5 min")
    embed.timestamp = discord.utils.utcnow()
    return embed


class SelecionarJogador(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="1️⃣ Selecione o jogador...", min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "SelecaoRankView" = self.view
        await interaction.response.defer(ephemeral=True)
        alvo = self.values[0]
        if not isinstance(alvo, discord.Member):
            alvo = interaction.guild.get_member(alvo.id) or alvo
        view.jogador = alvo
        await view.tentar_executar(interaction)


class SelecionarRank(discord.ui.Select):
    def __init__(self):
        opcoes = [
            discord.SelectOption(label=c["nome"], value=str(c["id"]), emoji=c["emoji"])
            for c in CARGOS_RANK
        ]
        super().__init__(placeholder="2️⃣ Selecione o novo rank...", min_values=1, max_values=1, options=opcoes, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "SelecaoRankView" = self.view
        await interaction.response.defer(ephemeral=True)
        view.novo_rank_id = int(self.values[0])
        await view.tentar_executar(interaction)


class SelecaoRankView(discord.ui.View):
    """Aparece (ephemeral) depois que a staff clica em Subir/Descer no painel.
    Só executa quando jogador E novo rank já foram escolhidos — assim o bot
    sempre acerta a mensagem, sem depender de adivinhar pelo diff de cargos."""

    def __init__(self, tipo: str):
        super().__init__(timeout=180)
        self.tipo = tipo  # "subir" ou "descer"
        self.jogador: discord.Member | None = None
        self.novo_rank_id: int | None = None
        self.add_item(SelecionarJogador())
        self.add_item(SelecionarRank())

    async def tentar_executar(self, interaction: discord.Interaction):
        if self.jogador is None or self.novo_rank_id is None:
            faltando = "o jogador" if self.jogador is None else "o novo rank"
            await interaction.followup.send(f"☑️ Escolha registrada. Ainda falta selecionar {faltando}.", ephemeral=True)
            return

        guild = interaction.guild
        novo_info = CARGO_MAP[self.novo_rank_id]
        novo_cargo = guild.get_role(self.novo_rank_id)
        if novo_cargo is None:
            await interaction.followup.send("⚠️ Esse cargo de rank não existe mais no servidor.", ephemeral=True)
            return

        cargos_rank_atuais = [r for r in self.jogador.roles if r.id in RANK_IDS]
        antigo_info = CARGO_MAP.get(cargos_rank_atuais[0].id) if cargos_rank_atuais else None

        try:
            if cargos_rank_atuais:
                await self.jogador.remove_roles(*cargos_rank_atuais, reason=f"Rank atualizado via !setup-rank ({self.tipo})")
            await self.jogador.add_roles(novo_cargo, reason=f"Rank atualizado via !setup-rank ({self.tipo})")
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão pra alterar os cargos desse jogador.", ephemeral=True)
            return

        channel = interaction.client.get_channel(JOGADORES_CHANNEL_ID)
        if channel is not None:
            if self.tipo == "subir":
                if antigo_info:
                    msg = (
                        f"⬆️ **{self.jogador.display_name}** upou do rank {antigo_info['emoji']} **{antigo_info['nome']}** "
                        f"para o rank {novo_info['emoji']} **{novo_info['nome']}**!"
                    )
                else:
                    msg = f"🎉 **{self.jogador.display_name}** entrou no clube com o rank {novo_info['emoji']} **{novo_info['nome']}**!"
            else:
                if antigo_info:
                    msg = (
                        f"⬇️ **{self.jogador.display_name}** desceu do rank {antigo_info['emoji']} **{antigo_info['nome']}** "
                        f"para o rank {novo_info['emoji']} **{novo_info['nome']}**."
                    )
                else:
                    msg = f"📉 **{self.jogador.display_name}** entrou no rank {novo_info['emoji']} **{novo_info['nome']}**."

            notif = await channel.send(msg)
            await notif.delete(delay=300)

            players_cog = interaction.client.get_cog("Players")
            if players_cog:
                await players_cog._editar_ou_criar(channel)

        await interaction.followup.send(
            f"✅ Rank de **{self.jogador.display_name}** atualizado pra {novo_info['emoji']} **{novo_info['nome']}**! "
            f"Mensagem enviada em {channel.mention if channel else '#canal de jogadores'}.",
            ephemeral=True,
        )
        self.stop()


class PainelRankView(discord.ui.View):
    """Painel fixo enviado pelo comando !setup-rank."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Subir de Rank", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="players_rank_subir")
    async def subir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**⬆️ Subida de rank**\nEscolha o jogador e o novo rank abaixo:",
            view=SelecaoRankView("subir"),
            ephemeral=True,
        )

    @discord.ui.button(label="Descer de Rank", emoji="⬇️", style=discord.ButtonStyle.danger, custom_id="players_rank_descer")
    async def descer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**⬇️ Descida de rank**\nEscolha o jogador e o novo rank abaixo:",
            view=SelecaoRankView("descer"),
            ephemeral=True,
        )


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot        = bot
        self.message_id = None
        self.bot.add_view(PainelRankView())  # mantém os botões funcionando após restart
        self.atualizar_lista.start()

    def cog_unload(self):
        self.atualizar_lista.cancel()

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
        await self._editar_ou_criar(channel)

    @atualizar_lista.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()

    async def _editar_ou_criar(self, channel: discord.TextChannel):
        embed = build_embed(channel.guild)
        if self.message_id:
            try:
                msg = await channel.fetch_message(self.message_id)
                await msg.edit(embed=embed)
                print(f"[PLAYERS] 🔄 Lista atualizada.")
                return
            except discord.NotFound:
                self.message_id = None
        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.embeds:
                if "TryHarders" in (msg.embeds[0].title or ""):
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
        """Envia o painel de atualização de rank (Subir/Descer) neste canal."""
        embed = discord.Embed(
            title="🎮 Painel de Atualização de Rank",
            description=(
                "Use os botões abaixo quando um jogador **subir** ou **descer** de rank.\n\n"
                "Você escolhe o jogador e o novo rank, o bot troca o cargo automaticamente "
                "e manda a mensagem certinha no canal de jogadores — sem depender de adivinhar "
                "a troca de cargo sozinho."
            ),
            color=0xD4A843,
        )
        await ctx.send(embed=embed, view=PainelRankView())
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
