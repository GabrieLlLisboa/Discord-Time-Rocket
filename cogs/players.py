import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────
#  Cog: Lista de Jogadores
#  Arquivo: cogs/players.py
# ─────────────────────────────────────────────

JOGADORES_CHANNEL_ID = 1514775408124367149

CARGOS = [
    {"nome": "Dono do Clube",      "id": 1511895253777649704, "emoji": "👑", "secao": "staff"},
    {"nome": "Sub-Dono",           "id": 1511894837790769204, "emoji": "🥈", "secao": "staff"},  # ⚠️ mesmo ID do cargo "Administrador" logo abaixo — confirma se não é engano
    {"nome": "Diretor",            "id": 1523835085475020932, "emoji": "🎖️", "secao": "staff"},
    {"nome": "Gerente",            "id": 1523835045872275566, "emoji": "🗂️", "secao": "staff"},
    {"nome": "Administrador",      "id": 1511894837790769204, "emoji": "🛡️", "secao": "staff"},
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

IDS_MONITORADOS = {c["id"] for c in CARGOS}
CARGO_MAP       = {c["id"]: c for c in CARGOS}
RANK_IDS        = {c["id"] for c in CARGOS if c["secao"] == "rank"}

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

    secao_atual = None
    membros_unicos = set()  # pra não contar 2x quem tem mais de um cargo monitorado (ex: staff + rank)

    for cargo_info in CARGOS:
        if cargo_info["secao"] != secao_atual:
            secao_atual = cargo_info["secao"]
            if secao_atual == "staff":
                embed.add_field(name="\u200b", value="```╔══════════  🏢  STAFF  ══════════╗```", inline=False)
            else:
                embed.add_field(name="\u200b", value="```╔══════════  🎮  RANKS  ══════════╗```", inline=False)

        membros = sorted(
            _membros_do_cargo(guild, cargo_info["id"]),
            key=lambda m: m.display_name.lower()
        )
        membros_unicos.update(m.id for m in membros)

        if membros:
            lista = "\n".join(f"  ▸  {m.display_name}" for m in membros)
        else:
            lista = "  *— nenhum jogador —*"

        embed.add_field(
            name=f"{cargo_info['emoji']}  **{cargo_info['nome']}**  `({len(membros)})`",
            value=f"{lista}\n\u200b",
            inline=False,
        )

    # Total de PESSOAS diferentes com pelo menos um cargo monitorado
    # (soma por cargo daria número errado, pois quem tem staff + rank seria contado 2x)
    embed.set_footer(text=f"⚡ {len(membros_unicos)} membros com cargo  •  Atualiza a cada 5 min")
    embed.timestamp = discord.utils.utcnow()
    return embed


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot        = bot
        self.message_id = None
        self.atualizar_lista.start()

    def cog_unload(self):
        self.atualizar_lista.cancel()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cargos_antes  = {r.id for r in before.roles}
        cargos_depois = {r.id for r in after.roles}
        ganhou  = (cargos_depois - cargos_antes) & IDS_MONITORADOS
        perdeu  = (cargos_antes - cargos_depois) & IDS_MONITORADOS
        if not ganhou and not perdeu:
            return
        channel = self.bot.get_channel(JOGADORES_CHANNEL_ID)
        if channel is None:
            return

        ganhou_rank  = ganhou & RANK_IDS
        perdeu_rank  = perdeu & RANK_IDS
        ganhou_staff = ganhou - RANK_IDS
        perdeu_staff = perdeu - RANK_IDS

        linhas = []
        ranks_consumidos = set()

        # Ganhou um rank novo: distingue "entrou no clube" de "upou de rank"
        for cid in ganhou_rank:
            info_novo = CARGO_MAP[cid]
            candidatos = perdeu_rank - ranks_consumidos
            rank_anterior_id = next(iter(candidatos), None)
            if rank_anterior_id is not None:
                info_antigo = CARGO_MAP[rank_anterior_id]
                ranks_consumidos.add(rank_anterior_id)
                linhas.append(
                    f"⬆️ **{after.display_name}** upou do rank {info_antigo['emoji']} **{info_antigo['nome']}** "
                    f"para o rank {info_novo['emoji']} **{info_novo['nome']}**!"
                )
            else:
                linhas.append(
                    f"🎉 **{after.display_name}** entrou no clube com o rank {info_novo['emoji']} **{info_novo['nome']}**!"
                )

        # Cargos de staff (não são rank) seguem a mensagem antiga
        for cid in ganhou_staff:
            info = CARGO_MAP[cid]
            linhas.append(f"📈 **{after.display_name}** subiu para {info['emoji']} **{info['nome']}**!")

        for cid in perdeu_staff:
            info = CARGO_MAP[cid]
            linhas.append(f"📉 **{after.display_name}** saiu de {info['emoji']} **{info['nome']}**.")

        # Rank perdido sem ganhar outro no lugar (rebaixamento "seco")
        for cid in perdeu_rank - ranks_consumidos:
            info = CARGO_MAP[cid]
            linhas.append(f"📉 **{after.display_name}** saiu do rank {info['emoji']} **{info['nome']}**.")

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

    @forcar_atualizacao.error
    async def forcar_atualizacao_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
