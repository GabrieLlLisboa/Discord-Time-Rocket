import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str

AMISTOSOS_CHANNEL_ID = 1514778555970621531
ADMIN_ROLE_ID        = 1511894837790769204

RANKS = {
    "Super Sonic Legend": 1514772134327488642,
    "Grand Champion":     1513343857125752992,
    "Champion":           1512304793534861313,
    "Diamante":           1512305401075466320,
    "Platina":            1512305547544625273,
    "Ouro":               1512571913849933956,
}

RANK_EMOJIS = {
    "Super Sonic Legend": "🌌",
    "Grand Champion":     "👑",
    "Champion":           "🏅",
    "Diamante":           "💎",
    "Platina":            "🪙",
    "Ouro":               "🥇",
}


def rank_info(role: discord.Role) -> tuple[str, str] | None:
    """Retorna (nome, emoji) se o cargo for um rank válido."""
    for nome, rid in RANKS.items():
        if role.id == rid:
            return nome, RANK_EMOJIS[nome]
    return None


# ── Botão de sair do amistoso ──────────────────────────────────────────────────
class SairAmistosoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🚪  Sair do Amistoso",
        style=discord.ButtonStyle.danger,
        custom_id="sair_amistoso"
    )
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro = interaction.user
        canal  = interaction.channel

        # Remove acesso ao canal
        await canal.set_permissions(membro, overwrite=None)

        # Remove do JSON e encontra o canal do anúncio
        amistosos = ler("amistosos")
        canal_anuncio_id = None
        for a in amistosos:
            if a.get("canal_id") == canal.id:
                if membro.id in a["confirmados"]:
                    a["confirmados"].remove(membro.id)
                canal_anuncio_id = AMISTOSOS_CHANNEL_ID
                break
        salvar("amistosos", amistosos)

        # Atualiza o embed do anúncio removendo o nick
        if canal_anuncio_id:
            canal_anuncio = interaction.client.get_channel(canal_anuncio_id)
            if canal_anuncio:
                async for msg in canal_anuncio.history(limit=20):
                    if msg.author == interaction.client.user and msg.embeds:
                        embed = msg.embeds[0]
                        # Procura o field de confirmados
                        novos_fields = []
                        for f in embed.fields:
                            if f.name.startswith("✅  Jogadores Confirmados"):
                                # Remove o nick da lista
                                linhas = [l for l in f.value.split("
") if membro.display_name not in l]
                                qtd = len(linhas)
                                if linhas:
                                    novos_fields.append(discord.ui.dynamic_field(
                                        name=f"✅  Jogadores Confirmados  `({qtd})`",
                                        value="
".join(linhas),
                                        inline=False
                                    ))
                                # Se lista ficou vazia, não adiciona o field
                            else:
                                novos_fields.append(f)

                        embed.clear_fields()
                        for f in novos_fields:
                            if hasattr(f, "name"):
                                embed.add_field(name=f.name, value=f.value, inline=f.inline)

                        await msg.edit(embed=embed)
                        break

        # Avisa no canal que saiu
        await canal.send(f"🚪 **{membro.display_name}** saiu do amistoso.")

        await interaction.response.send_message(
            "✅ Você saiu do amistoso e perdeu o acesso ao canal.",
            ephemeral=True
        )
        print(f"[AMISTOSO] 🚪 {membro} saiu do amistoso no canal #{canal.name}.")


# ── Botão de confirmar presença ────────────────────────────────────────────────
class ConfirmarPresencaView(discord.ui.View):
    def __init__(self, rank_alvo: str, rank_id: int, canal_amistoso_id: int, rank_ids_extras: list[int] = None):
        super().__init__(timeout=None)
        self.rank_alvo         = rank_alvo
        self.rank_id           = rank_id
        self.rank_ids_extras   = rank_ids_extras or [rank_id]
        self.canal_amistoso_id = canal_amistoso_id
        self.confirmados: list[tuple[str, int]] = []

    @discord.ui.button(
        label="✅  Confirmar Presença",
        style=discord.ButtonStyle.success,
        custom_id="confirmar_amistoso"
    )
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro     = interaction.user
        ids_cargos = {r.id for r in membro.roles}

        if not any(rid in ids_cargos for rid in self.rank_ids_extras):
            await interaction.response.send_message(
                f"❌ Apenas jogadores **{self.rank_alvo}** podem confirmar presença neste amistoso.",
                ephemeral=True
            )
            return

        if any(mid == membro.id for _, mid in self.confirmados):
            await interaction.response.send_message(
                "⚠️ Você já confirmou presença neste amistoso!",
                ephemeral=True
            )
            return

        self.confirmados.append((membro.display_name, membro.id))

        # Atualiza embed do anúncio
        embed = interaction.message.embeds[0]
        novos_fields = [f for f in embed.fields if not f.name.startswith("✅  Jogadores Confirmados")]
        embed.clear_fields()
        for f in novos_fields:
            embed.add_field(name=f.name, value=f.value, inline=f.inline)
        lista = "\n".join(f"  ▸  {nome}" for nome, _ in self.confirmados)
        embed.add_field(
            name=f"✅  Jogadores Confirmados  `({len(self.confirmados)})`",
            value=lista,
            inline=False
        )
        await interaction.message.edit(embed=embed, view=self)

        # Salva no JSON
        amistosos = ler("amistosos")
        for a in amistosos:
            if a.get("canal_id") == self.canal_amistoso_id:
                if membro.id not in a["confirmados"]:
                    a["confirmados"].append(membro.id)
                break
        salvar("amistosos", amistosos)

        # Libera acesso ao canal
        canal_amistoso = interaction.client.get_channel(self.canal_amistoso_id)
        if canal_amistoso:
            await canal_amistoso.set_permissions(
                membro,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
            # Avisa no canal do amistoso
            await canal_amistoso.send(
                f"✅ {membro.mention} confirmou presença!"
            )

        await interaction.response.send_message(
            f"✅ Presença confirmada! Você agora tem acesso a {canal_amistoso.mention if canal_amistoso else 'o canal do amistoso'}. 🚀",
            ephemeral=True
        )
        print(f"[AMISTOSO] ✅ {membro} confirmou presença.")


# ── Modal ──────────────────────────────────────────────────────────────────────
async def criar_amistoso(
    interaction: discord.Interaction,
    adversario: str,
    data_hora: str,
    rank1: discord.Role,
    info_extra: str,
    rank2: discord.Role | None,
):
    guild = interaction.guild

    # Valida ranks
    info1 = rank_info(rank1)
    if info1 is None:
        await interaction.response.send_message(
            f"❌ O cargo {rank1.mention} não é um rank válido.", ephemeral=True
        )
        return

    ranks_validos   = [(rank1, info1)]
    ranks_ids       = [rank1.id]
    mencoes         = [rank1.mention]
    nomes_ranks     = [info1[0]]
    emojis_ranks    = [info1[1]]

    if rank2 and rank2.id != rank1.id:
        info2 = rank_info(rank2)
        if info2 is None:
            await interaction.response.send_message(
                f"❌ O cargo {rank2.mention} não é um rank válido.", ephemeral=True
            )
            return
        ranks_validos.append((rank2, info2))
        ranks_ids.append(rank2.id)
        mencoes.append(rank2.mention)
        nomes_ranks.append(info2[0])
        emojis_ranks.append(info2[1])

    rank_display = " + ".join(f"{e} {n}" for e, n in zip(emojis_ranks, nomes_ranks))
    mencao_str   = " ".join(mencoes)
    rank_salvo   = " + ".join(nomes_ranks)

    nome_canal = f"amistoso-{adversario.lower().strip()}"
    nome_canal = "".join(c if c.isalnum() or c == "-" else "-" for c in nome_canal)[:50]

    admin_role = guild.get_role(ADMIN_ROLE_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )

    canal_ref      = guild.get_channel(AMISTOSOS_CHANNEL_ID)
    categoria      = canal_ref.category if canal_ref else None
    canal_amistoso = await guild.create_text_channel(
        name=nome_canal,
        overwrites=overwrites,
        category=categoria,
        reason=f"Amistoso vs {adversario} criado por {interaction.user}"
    )

    embed = discord.Embed(title="⚽  AMISTOSO ANUNCIADO", color=0xD4A843)
    embed.add_field(name="​", value="```╔══════════  📋  DETALHES  ══════════╗```", inline=False)
    embed.add_field(name="🆚  Adversário",  value=f"**{adversario}**",   inline=True)
    embed.add_field(name="📅  Data / Hora", value=f"**{data_hora}**",    inline=True)
    embed.add_field(name="🏅  Rank",        value=rank_display,          inline=True)
    if info_extra:
        embed.add_field(name="📝  Informações", value=info_extra, inline=False)
    embed.add_field(
        name="​",
        value=f"🔔 {mencao_str} — Confirme sua presença abaixo!
📁 Canal do amistoso: {canal_amistoso.mention}",
        inline=False
    )
    embed.set_footer(text=f"Anunciado por {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    canal_anuncio = interaction.client.get_channel(AMISTOSOS_CHANNEL_ID)
    if canal_anuncio is None:
        await interaction.response.send_message("❌ Canal de amistosos não encontrado.", ephemeral=True)
        return

    # Usa o primeiro rank_id para validar presença (ou ambos — veja ConfirmarPresencaView)
    view_confirmacao = ConfirmarPresencaView(
        rank_alvo=rank_salvo,
        rank_id=ranks_ids[0],
        canal_amistoso_id=canal_amistoso.id,
        rank_ids_extras=ranks_ids,
    )
    msg_anuncio = await canal_anuncio.send(content=mencao_str, embed=embed, view=view_confirmacao)

    cog = interaction.client.cogs.get("Friendly")
    if cog:
        cog.registrar(msg_anuncio.id, canal_amistoso.id)

    amistosos = ler("amistosos")
    amistosos.append({
        "id":          len(amistosos) + 1,
        "adversario":  adversario,
        "data":        data_hora,
        "rank":        rank_salvo,
        "resultado":   None,
        "placar":      "",
        "confirmados": [],
        "canal_id":    canal_amistoso.id,
        "criado_em":   agora_str(),
    })
    salvar("amistosos", amistosos)

    embed_canal = discord.Embed(
        title=f"⚽ Amistoso vs {adversario}",
        description=(
            f"Bem-vindos ao canal do amistoso!

"
            f"**🏅 Rank:** {rank_display}
"
            f"**📅 Data:** {data_hora}
"
            f"{'**📝 Info:** ' + info_extra if info_extra else ''}

"
            f"Se quiser desistir, clique no botão abaixo."
        ),
        color=0xD4A843
    )
    await canal_amistoso.send(embed=embed_canal, view=SairAmistosoView())

    await interaction.response.send_message(
        f"✅ Amistoso anunciado! Canal criado: {canal_amistoso.mention}",
        ephemeral=True
    )
    print(f"[AMISTOSO] ✅ {interaction.user} anunciou amistoso vs {adversario} — {rank_salvo}")


# ── Cog ───────────────────────────────────────────────────────────────────────
class Friendly(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.amistoso_map: dict[int, int] = {}

    def registrar(self, message_id: int, canal_id: int):
        self.amistoso_map[message_id] = canal_id

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.channel.id != AMISTOSOS_CHANNEL_ID:
            return
        canal_id = self.amistoso_map.pop(message.id, None)
        if canal_id is None:
            return
        canal = self.bot.get_channel(canal_id)
        if canal:
            await canal.delete(reason="Mensagem do amistoso deletada — canal removido automaticamente.")
            print(f"[AMISTOSO] 🗑️ Canal {canal.name} deletado junto com o anúncio.")

    @app_commands.command(name="amistoso", description="Anuncia um amistoso no canal de amistosos.")
    @app_commands.checks.has_role(ADMIN_ROLE_ID)
    @app_commands.describe(
        adversario="Nome do time adversário",
        data_hora="Data e horário (ex: 15/06 às 20h00)",
        rank1="Cargo do rank principal",
        rank2="Segundo cargo de rank (opcional)",
        info_extra="Informações extras (opcional)",
    )
    async def amistoso(
        self,
        interaction: discord.Interaction,
        adversario: str,
        data_hora: str,
        rank1: discord.Role,
        rank2: discord.Role = None,
        info_extra: str = "",
    ):
        await criar_amistoso(interaction, adversario, data_hora, rank1, info_extra, rank2)

    @amistoso.error
    async def amistoso_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem anunciar amistosos.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Friendly(bot))
