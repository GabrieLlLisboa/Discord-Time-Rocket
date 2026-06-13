import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────
#  Cog: Amistosos
#  Arquivo: cogs/friendly.py
#  Slash: /amistoso
# ─────────────────────────────────────────────

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


def encontrar_rank(digitado: str) -> str | None:
    """
    Busca rank pelo nome.
    Prioridade: exato (case-insensitive) → começa com → contém.
    Evita 'Champion' encontrar 'Grand Champion'.
    """
    d = digitado.strip().lower()

    # 1. Correspondência exata
    for nome in RANKS:
        if nome.lower() == d:
            return nome

    # 2. Começa com o que foi digitado
    for nome in RANKS:
        if nome.lower().startswith(d):
            return nome

    # 3. O que foi digitado começa com o nome do rank (ex: digita nome completo errado)
    for nome in RANKS:
        if d.startswith(nome.lower()):
            return nome

    return None


# ── Botão de confirmar presença ────────────────────────────────────────────────
class ConfirmarPresencaView(discord.ui.View):
    def __init__(self, rank_alvo: str, rank_id: int, canal_amistoso_id: int):
        super().__init__(timeout=None)
        self.rank_alvo         = rank_alvo
        self.rank_id           = rank_id
        self.canal_amistoso_id = canal_amistoso_id
        self.confirmados: list[tuple[str, int]] = []  # (display_name, member_id)

    @discord.ui.button(
        label="✅  Confirmar Presença",
        style=discord.ButtonStyle.success,
        custom_id="confirmar_amistoso"
    )
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro     = interaction.user
        ids_cargos = {r.id for r in membro.roles}

        # Só o rank correto pode confirmar
        if self.rank_id not in ids_cargos:
            emoji = RANK_EMOJIS.get(self.rank_alvo, "")
            await interaction.response.send_message(
                f"❌ Apenas jogadores **{emoji} {self.rank_alvo}** podem confirmar presença neste amistoso.",
                ephemeral=True
            )
            return

        # Já confirmou?
        if any(mid == membro.id for _, mid in self.confirmados):
            await interaction.response.send_message(
                "⚠️ Você já confirmou presença neste amistoso!",
                ephemeral=True
            )
            return

        self.confirmados.append((membro.display_name, membro.id))

        # Atualiza embed
        embed = interaction.message.embeds[0]
        novos_fields = [f for f in embed.fields if f.name != f"✅  Jogadores Confirmados  `({len(self.confirmados) - 1})`"
                        and not f.name.startswith("✅  Jogadores Confirmados")]
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

        # Libera acesso ao canal do amistoso
        canal_amistoso = interaction.client.get_channel(self.canal_amistoso_id)
        if canal_amistoso:
            await canal_amistoso.set_permissions(
                membro,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        await interaction.response.send_message(
            f"✅ Presença confirmada! Você agora tem acesso a {canal_amistoso.mention if canal_amistoso else 'o canal do amistoso'}. 🚀",
            ephemeral=True
        )
        print(f"[AMISTOSO] ✅ {membro} confirmou presença.")


# ── Modal ──────────────────────────────────────────────────────────────────────
class AmistosoModal(discord.ui.Modal, title="📋  Anunciar Amistoso"):
    adversario = discord.ui.TextInput(
        label="Adversário",
        placeholder="Ex: Time Fenix, NRG...",
        max_length=50,
    )
    data = discord.ui.TextInput(
        label="Data e Horário",
        placeholder="Ex: 15/06 às 20h00",
        max_length=50,
    )
    rank = discord.ui.TextInput(
        label="Rank",
        placeholder="Ouro / Platina / Diamante / Champion / Grand Champion / SSL",
        max_length=50,
    )
    info_extra = discord.ui.TextInput(
        label="Informações extras (opcional)",
        placeholder="Ex: BO3, regras especiais...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        rank_encontrado = encontrar_rank(self.rank.value)

        if rank_encontrado is None:
            await interaction.response.send_message(
                f"❌ Rank **{self.rank.value}** não reconhecido.\n"
                f"Use: `{' / '.join(RANKS.keys())}`",
                ephemeral=True
            )
            return

        rank_id    = RANKS[rank_encontrado]
        rank_emoji = RANK_EMOJIS[rank_encontrado]
        guild      = interaction.guild
        cargo      = guild.get_role(rank_id)
        mencao     = cargo.mention if cargo else f"@{rank_encontrado}"

        # Nome do canal: amistoso-nomedoadversario (sem espaços/caracteres especiais)
        nome_canal = f"amistoso-{self.adversario.value.lower().strip()}"
        nome_canal = "".join(c if c.isalnum() or c == "-" else "-" for c in nome_canal)
        nome_canal = nome_canal[:50]

        # Permissões do canal — só admin vê inicialmente
        admin_role = guild.get_role(ADMIN_ROLE_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        # Cria o canal de amistoso na mesma categoria do canal de amistosos
        canal_ref      = guild.get_channel(AMISTOSOS_CHANNEL_ID)
        categoria      = canal_ref.category if canal_ref else None
        canal_amistoso = await guild.create_text_channel(
            name=nome_canal,
            overwrites=overwrites,
            category=categoria,
            reason=f"Amistoso vs {self.adversario.value} criado por {interaction.user}"
        )

        # Monta embed
        embed = discord.Embed(
            title="⚽  AMISTOSO ANUNCIADO",
            color=0xD4A843,
        )
        embed.add_field(
            name="\u200b",
            value="```╔══════════  📋  DETALHES  ══════════╗```",
            inline=False
        )
        embed.add_field(name="🆚  Adversário",  value=f"**{self.adversario.value}**", inline=True)
        embed.add_field(name="📅  Data / Hora", value=f"**{self.data.value}**",       inline=True)
        embed.add_field(name=f"{rank_emoji}  Rank", value=f"**{rank_encontrado}**",   inline=True)

        if self.info_extra.value:
            embed.add_field(name="📝  Informações", value=self.info_extra.value, inline=False)

        embed.add_field(
            name="\u200b",
            value=f"🔔 {mencao} — Confirme sua presença abaixo!\n📁 Canal do amistoso: {canal_amistoso.mention}",
            inline=False
        )
        embed.set_footer(
            text=f"Anunciado por {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()

        # Envia no canal de amistosos
        canal_anuncio = interaction.client.get_channel(AMISTOSOS_CHANNEL_ID)
        if canal_anuncio is None:
            await interaction.response.send_message("❌ Canal de amistosos não encontrado.", ephemeral=True)
            return

        view = ConfirmarPresencaView(
            rank_alvo=rank_encontrado,
            rank_id=rank_id,
            canal_amistoso_id=canal_amistoso.id
        )
        await canal_anuncio.send(content=mencao, embed=embed, view=view)

        # Envia mensagem inicial no canal do amistoso
        embed_canal = discord.Embed(
            title=f"⚽ Amistoso vs {self.adversario.value}",
            description=(
                f"Bem-vindos ao canal do amistoso!\n\n"
                f"**{rank_emoji} Rank:** {rank_encontrado}\n"
                f"**📅 Data:** {self.data.value}\n"
                f"{'**📝 Info:** ' + self.info_extra.value if self.info_extra.value else ''}\n\n"
                f"Jogadores confirmados ganham acesso automaticamente ao confirmar presença."
            ),
            color=0xD4A843
        )
        await canal_amistoso.send(embed=embed_canal)

        await interaction.response.send_message(
            f"✅ Amistoso anunciado! Canal criado: {canal_amistoso.mention}",
            ephemeral=True
        )
        print(f"[AMISTOSO] ✅ {interaction.user} anunciou amistoso vs {self.adversario.value} — {rank_encontrado}")


# ── Cog ───────────────────────────────────────────────────────────────────────
class Friendly(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="amistoso", description="Anuncia um amistoso no canal de amistosos.")
    @app_commands.checks.has_role(ADMIN_ROLE_ID)
    async def amistoso(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AmistosoModal())

    @amistoso.error
    async def amistoso_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem anunciar amistosos.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Friendly(bot))
