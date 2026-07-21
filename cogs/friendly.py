import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str

AMISTOSOS_CHANNEL_ID = 1514778555970621531

# Cargos autorizados a gerenciar/finalizar amistosos (mesmos cargos usados
# pelo sistema de coaches — ver cogs/coach_config.py). Antes havia apenas
# um ADMIN_ROLE_ID; agora são dois cargos, e qualquer um dos dois basta.
ADMIN_ROLE_IDS = {
    1511895253777649704,
    1529150684296122438,
}

RANKS = {
    "Super Sonic Legend": 1529152122942390366,
    "Grand Champion":     1529152259630305402,
    "Champion":           1529152654629142679,
    "Diamante":           1529153925486215350,
    "Platina":            1529154068314849450,
}

RANK_EMOJIS = {
    "Super Sonic Legend": "🌌",
    "Grand Champion":     "👑",
    "Champion":           "🏅",
    "Diamante":           "💎",
    "Platina":            "🪙",
}


def rank_info(role: discord.Role):
    for nome, rid in RANKS.items():
        if role.id == rid:
            return nome, RANK_EMOJIS[nome]
    return None


def _construir_lista_confirmados(guild: discord.Guild, ids_confirmados: list) -> str:
    """Monta o texto da lista de confirmados SEMPRE a partir dos IDs
    salvos no JSON (fonte única de verdade) — nunca de uma lista guardada
    em memória, que pode ficar desincronizada (ex: alguém sai e a lista
    em memória de outra view não fica sabendo)."""
    linhas = []
    for mid in ids_confirmados:
        membro = guild.get_member(mid)
        nome = membro.display_name if membro else f"Usuário {mid}"
        linhas.append(f"  ▸  {nome}")
    return "\n".join(linhas)


async def _atualizar_embed_confirmados(mensagem: discord.Message, guild: discord.Guild, ids_confirmados: list):
    """Reconstrói o campo '✅ Jogadores Confirmados' do embed de anúncio a
    partir da lista canônica de IDs (JSON), e salva o embed editado."""
    if not mensagem.embeds:
        return
    embed = mensagem.embeds[0]
    outros_campos = [f for f in embed.fields if not f.name.startswith("✅  Jogadores Confirmados")]
    embed.clear_fields()
    for f in outros_campos:
        embed.add_field(name=f.name, value=f.value, inline=f.inline)
    lista = _construir_lista_confirmados(guild, ids_confirmados)
    embed.add_field(
        name=f"✅  Jogadores Confirmados  `({len(ids_confirmados)})`",
        value=lista if lista else "  *— ninguém ainda —*",
        inline=False,
    )
    try:
        await mensagem.edit(embed=embed)
    except discord.HTTPException as e:
        print(f"[AMISTOSO] ⚠️ Erro ao atualizar embed de confirmados: {e}")


# ── Botão de sair ──────────────────────────────────────────────────────────────
class SairAmistosoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚪  Sair do Amistoso", style=discord.ButtonStyle.danger, custom_id="sair_amistoso")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro = interaction.user
        canal  = interaction.channel

        await canal.set_permissions(membro, overwrite=None)

        amistosos = ler("amistosos")
        amistoso_atual = None
        for a in amistosos:
            if a.get("canal_id") == canal.id:
                if membro.id in a["confirmados"]:
                    a["confirmados"].remove(membro.id)
                amistoso_atual = a
                break
        salvar("amistosos", amistosos)

        # Atualiza embed do anúncio a partir do JSON (fonte única de verdade
        # — assim a próxima tentativa de confirmar presença desse membro,
        # seja pela mesma view ou depois de um restart do bot, já vê que
        # ele não está mais confirmado)
        if amistoso_atual and amistoso_atual.get("msg_anuncio_id"):
            canal_anuncio = interaction.client.get_channel(AMISTOSOS_CHANNEL_ID)
            if canal_anuncio:
                try:
                    msg_anuncio = await canal_anuncio.fetch_message(amistoso_atual["msg_anuncio_id"])
                    await _atualizar_embed_confirmados(msg_anuncio, interaction.guild, amistoso_atual["confirmados"])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await canal.send(f"🚪 **{membro.display_name}** saiu do amistoso.")
        await interaction.response.send_message("✅ Você saiu do amistoso e perdeu o acesso ao canal.", ephemeral=True)
        print(f"[AMISTOSO] 🚪 {membro} saiu do amistoso no canal #{canal.name}.")


# ── Botão de confirmar presença ────────────────────────────────────────────────
class ConfirmarPresencaView(discord.ui.View):
    def __init__(self, rank_alvo: str, rank_id: int, canal_amistoso_id: int, rank_ids_extras: list = None):
        super().__init__(timeout=None)
        self.rank_alvo         = rank_alvo
        self.rank_id           = rank_id
        self.rank_ids_extras   = rank_ids_extras or [rank_id]
        self.canal_amistoso_id = canal_amistoso_id
        # OBS: NÃO guarda mais a lista de confirmados aqui em memória.
        # Isso era a causa do bug de "já confirmou presença" mesmo depois
        # de sair — e também não sobrevivia a um restart do bot. Agora
        # tudo lê/escreve direto no JSON (self.cog.dados / arquivo
        # "amistosos"), que é a única fonte de verdade.

    def _buscar_amistoso(self, amistosos: list):
        for a in amistosos:
            if a.get("canal_id") == self.canal_amistoso_id:
                return a
        return None

    @discord.ui.button(label="✅  Confirmar Presença", style=discord.ButtonStyle.success, custom_id="confirmar_amistoso")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro     = interaction.user
        ids_cargos = {r.id for r in membro.roles}

        if not any(rid in ids_cargos for rid in self.rank_ids_extras):
            await interaction.response.send_message(
                f"❌ Apenas jogadores **{self.rank_alvo}** podem confirmar presença neste amistoso.",
                ephemeral=True
            )
            return

        amistosos = ler("amistosos")
        amistoso = self._buscar_amistoso(amistosos)
        if amistoso is None:
            await interaction.response.send_message("⚠️ Não achei os dados desse amistoso — fala com um admin.", ephemeral=True)
            return

        if membro.id in amistoso["confirmados"]:
            await interaction.response.send_message("⚠️ Você já confirmou presença neste amistoso!", ephemeral=True)
            return

        amistoso["confirmados"].append(membro.id)
        salvar("amistosos", amistosos)

        # Atualiza embed do anúncio a partir da lista canônica (JSON)
        await _atualizar_embed_confirmados(interaction.message, interaction.guild, amistoso["confirmados"])

        # Libera acesso ao canal e notifica
        canal_amistoso = interaction.client.get_channel(self.canal_amistoso_id)
        if canal_amistoso:
            await canal_amistoso.set_permissions(
                membro, view_channel=True, send_messages=True, read_message_history=True
            )
            await canal_amistoso.send(f"✅ {membro.mention} confirmou presença!")

        await interaction.response.send_message(
            f"✅ Presença confirmada! Você agora tem acesso a {canal_amistoso.mention if canal_amistoso else 'o canal do amistoso'}. 🔥",
            ephemeral=True
        )
        print(f"[AMISTOSO] ✅ {membro} confirmou presença.")


# ── Lógica de criação do amistoso ─────────────────────────────────────────────
async def criar_amistoso(
    interaction: discord.Interaction,
    adversario: str,
    data_hora: str,
    rank1: discord.Role,
    info_extra: str,
    rank2: discord.Role = None,
):
    guild = interaction.guild

    info1 = rank_info(rank1)
    if info1 is None:
        await interaction.response.send_message(f"❌ O cargo {rank1.mention} não é um rank válido.", ephemeral=True)
        return

    ranks_ids    = [rank1.id]
    nomes_ranks  = [info1[0]]
    emojis_ranks = [info1[1]]

    if rank2 and rank2.id != rank1.id:
        info2 = rank_info(rank2)
        if info2 is None:
            await interaction.response.send_message(f"❌ O cargo {rank2.mention} não é um rank válido.", ephemeral=True)
            return
        ranks_ids.append(rank2.id)
        nomes_ranks.append(info2[0])
        emojis_ranks.append(info2[1])

    rank_display = " + ".join(f"{e} {n}" for e, n in zip(emojis_ranks, nomes_ranks))
    mencao_str   = " ".join(guild.get_role(rid).mention for rid in ranks_ids if guild.get_role(rid))
    rank_salvo   = " + ".join(nomes_ranks)

    nome_canal = "amistoso-" + "".join(c if c.isalnum() or c == "-" else "-" for c in adversario.lower().strip())
    nome_canal = nome_canal[:50]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for admin_role_id in ADMIN_ROLE_IDS:
        admin_role = guild.get_role(admin_role_id)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    canal_ref      = guild.get_channel(AMISTOSOS_CHANNEL_ID)
    categoria      = canal_ref.category if canal_ref else None
    canal_amistoso = await guild.create_text_channel(
        name=nome_canal, overwrites=overwrites, category=categoria,
        reason=f"Amistoso vs {adversario} criado por {interaction.user}"
    )

    embed = discord.Embed(title="🚗  RACHA ANUNCIADO", color=0xFF5A1F)
    embed.add_field(name="\u200b", value="```╔══════════  📋  DETALHES  ══════════╗```", inline=False)
    embed.add_field(name="🆚  Adversário",  value=f"**{adversario}**", inline=True)
    embed.add_field(name="📅  Data / Hora", value=f"**{data_hora}**",  inline=True)
    embed.add_field(name="🏅  Rank",        value=rank_display,        inline=True)
    if info_extra:
        embed.add_field(name="📝  Informações", value=info_extra, inline=False)
    embed.add_field(
        name="\u200b",
        value=f"🔔 {mencao_str} — Confirme sua presença abaixo!\n📁 Canal do amistoso: {canal_amistoso.mention}",
        inline=False
    )
    embed.set_footer(text=f"Anunciado por {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    canal_anuncio = interaction.client.get_channel(AMISTOSOS_CHANNEL_ID)
    if canal_anuncio is None:
        await interaction.response.send_message("❌ Canal de amistosos não encontrado.", ephemeral=True)
        return

    view_conf   = ConfirmarPresencaView(rank_alvo=rank_salvo, rank_id=ranks_ids[0], canal_amistoso_id=canal_amistoso.id, rank_ids_extras=ranks_ids)
    msg_anuncio = await canal_anuncio.send(content=mencao_str, embed=embed, view=view_conf)

    cog = interaction.client.cogs.get("Friendly")
    if cog:
        cog.registrar(msg_anuncio.id, canal_amistoso.id)

    amistosos = ler("amistosos")
    amistosos.append({
        "id": len(amistosos) + 1, "adversario": adversario, "data": data_hora,
        "rank": rank_salvo, "resultado": None, "placar": "", "confirmados": [],
        "canal_id": canal_amistoso.id, "criado_em": agora_str(),
        "msg_anuncio_id": msg_anuncio.id,
        "rank_id": ranks_ids[0],
        "rank_ids_extras": ranks_ids,
    })
    salvar("amistosos", amistosos)

    embed_canal = discord.Embed(
        title=f"🚗 Amistoso vs {adversario}",
        description=(
            f"Bem-vindos ao canal do amistoso!\n\n"
            f"**🏅 Rank:** {rank_display}\n"
            f"**📅 Data:** {data_hora}\n"
            + (f"**📝 Info:** {info_extra}\n" if info_extra else "") +
            "\nSe quiser desistir, clique no botão abaixo."
        ),
        color=0xFF5A1F
    )
    await canal_amistoso.send(embed=embed_canal, view=SairAmistosoView())
    await interaction.response.send_message(f"✅ Amistoso anunciado! Canal criado: {canal_amistoso.mention}", ephemeral=True)
    print(f"[AMISTOSO] ✅ {interaction.user} anunciou amistoso vs {adversario} — {rank_salvo}")


# ── Cog ───────────────────────────────────────────────────────────────────────
class Friendly(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.amistoso_map: dict[int, int] = {}

        # Reconstrói os botões (✅ Confirmar Presença / 🚪 Sair do Amistoso)
        # de todo amistoso que ainda não tem resultado registrado — assim,
        # se o bot reiniciar no meio de um amistoso em andamento, os
        # botões continuam funcionando normalmente (nada de "essa
        # interação falhou" pro pessoal que for confirmar presença depois
        # do restart).
        self.bot.add_view(SairAmistosoView())  # custom_id fixo, serve pra qualquer canal de amistoso

        for a in ler("amistosos"):
            if a.get("resultado") is not None:
                continue  # já finalizado — não precisa mais reativar os botões dele

            msg_id   = a.get("msg_anuncio_id")
            canal_id = a.get("canal_id")
            rank_id  = a.get("rank_id")
            if msg_id is None or canal_id is None:
                # Amistosos criados antes dessa atualização não têm esses
                # dados salvos — sem eles não dá pra reconstruir a view
                # com segurança, então só pula (não trava o bot).
                continue

            view = ConfirmarPresencaView(
                rank_alvo=a.get("rank", ""),
                rank_id=rank_id,
                canal_amistoso_id=canal_id,
                rank_ids_extras=a.get("rank_ids_extras") or ([rank_id] if rank_id else []),
            )
            self.bot.add_view(view, message_id=msg_id)
            self.amistoso_map[msg_id] = canal_id

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
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
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
            await interaction.response.send_message("❌ Apenas **Administradores** podem anunciar amistosos.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Friendly(bot))
