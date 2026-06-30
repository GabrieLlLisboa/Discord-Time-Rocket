import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────
#  Cog: Lista de Jogadores
#  Arquivo: cogs/players.py
# ─────────────────────────────────────────────

JOGADORES_CHANNEL_ID = 1514775408124367149

CARGOS = [
    {"nome": "Administrador",      "id": 1511894837790769204, "emoji": "🛡️", "secao": "staff"},
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


def build_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🚀  TryHarders RL — Time de Rocket League",
        color=0xD4A843,
    )

    secao_atual = None

    for cargo_info in CARGOS:
        if cargo_info["secao"] != secao_atual:
            secao_atual = cargo_info["secao"]
            if secao_atual == "staff":
                embed.add_field(name="\u200b", value="```╔══════════  🏢  STAFF  ══════════╗```", inline=False)
            else:
                embed.add_field(name="\u200b", value="```╔══════════  🎮  RANKS  ══════════╗```", inline=False)

        cargo = guild.get_role(cargo_info["id"])
        if cargo is None:
            continue

        membros = sorted(
            [m for m in cargo.members if not m.bot],
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

    total = sum(
        len([m for m in guild.get_role(c["id"]).members if not m.bot])
        for c in CARGOS if guild.get_role(c["id"])
    )

    embed.set_footer(text=f"⚡ {total} membros com cargo  •  Atualiza a cada 5 min")
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

    @forcar_atualizacao.error
    async def forcar_atualizacao_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas **Administradores** podem usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
