import time

import discord
from discord.ext import commands, tasks
from discord import app_commands
from cogs.backup import ler, salvar, agora_str
from cogs import mod_utils as mu
from cogs.friendly import (
    _parse_data_hora,
    rank_info,
    ADMIN_ROLE_IDS,
    CATEGORIA_VOZ_AMISTOSOS_ID,
    _MARCOS_LEMBRETE,
    _TEXTO_TEMPO,
)


# Canal onde as partidas de campeonato são anunciadas. Deixe 0 pra usar o
# canal onde o comando /partida-campeonato foi digitado (mais simples de
# configurar, não precisa saber o ID de nenhum canal na mão).
CAMPEONATO_PARTIDAS_CHANNEL_ID = 0

# Categoria de voz das calls de partida de campeonato. Deixe 0 pra reusar
# a mesma categoria de voz usada pelos amistosos.
CATEGORIA_VOZ_CAMPEONATO_ID = 0

# Identidade visual própria da partida de campeonato (diferente do /amistoso,
# que usa dourado 0xD4A843).
COR_CAMPEONATO = 0x9B59B6  # roxo


_AVISO_SAIR_CANAL = (
    "\n\n📌 Gostaríamos de lembrar que, se você não pode participar, aperte "
    "no botão de sair anexado a esta mensagem — isso torna tudo mais organizado."
)
_AVISO_SAIR_DM = (
    "\n\n📌 Gostaríamos de lembrar que, se você não pode participar, aperte "
    "no botão de sair no canal da partida — isso torna tudo mais organizado."
)


def _construir_lista_confirmados(guild: discord.Guild, ids_confirmados: list) -> str:
    linhas = []
    for mid in ids_confirmados:
        membro = guild.get_member(mid)
        nome = membro.display_name if membro else f"Usuário {mid}"
        linhas.append(f"  ▸  {nome}")
    return "\n".join(linhas)


async def _atualizar_embed_confirmados(mensagem: discord.Message, guild: discord.Guild, ids_confirmados: list):
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
        print(f"[PARTIDA-CAMPEONATO] ⚠️ Erro ao atualizar embed de confirmados: {e}")


class SairPartidaCampeonatoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏁  Sair da Partida", style=discord.ButtonStyle.danger, custom_id="sair_partida_campeonato")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro = interaction.user
        canal  = interaction.channel

        await canal.set_permissions(membro, overwrite=None)

        partidas = ler("partidas_campeonato")
        partida_atual = None
        for p in partidas:
            if p.get("canal_id") == canal.id:
                if membro.id in p["confirmados"]:
                    p["confirmados"].remove(membro.id)
                partida_atual = p
                break
        salvar("partidas_campeonato", partidas)

        if partida_atual:
            canal_voz_id = partida_atual.get("canal_voz_id")
            if canal_voz_id:
                canal_voz = interaction.client.get_channel(canal_voz_id)
                if canal_voz:
                    try:
                        await canal_voz.set_permissions(membro, overwrite=None)
                    except discord.HTTPException as e:
                        print(f"[PARTIDA-CAMPEONATO] ⚠️ Erro ao remover acesso do canal de voz pra {membro}: {e}")

        if partida_atual and partida_atual.get("msg_anuncio_id"):
            canal_anuncio_id = partida_atual.get("canal_anuncio_id")
            canal_anuncio = interaction.client.get_channel(canal_anuncio_id) if canal_anuncio_id else None
            if canal_anuncio:
                try:
                    msg_anuncio = await canal_anuncio.fetch_message(partida_atual["msg_anuncio_id"])
                    await _atualizar_embed_confirmados(msg_anuncio, interaction.guild, partida_atual["confirmados"])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await canal.send(f"🚪 **{membro.display_name}** saiu da partida.")
        await interaction.response.send_message("✅ Você saiu da partida e perdeu o acesso ao canal.", ephemeral=True)
        print(f"[PARTIDA-CAMPEONATO] 🚪 {membro} saiu da partida no canal #{canal.name}.")


class ConfirmarPresencaCampeonatoView(discord.ui.View):
    def __init__(self, rank_alvo: str, rank_id: int, canal_partida_id: int, rank_ids_extras: list = None):
        super().__init__(timeout=None)
        self.rank_alvo        = rank_alvo
        self.rank_id          = rank_id
        self.rank_ids_extras  = rank_ids_extras or [rank_id]
        self.canal_partida_id = canal_partida_id

    def _buscar_partida(self, partidas: list):
        for p in partidas:
            if p.get("canal_id") == self.canal_partida_id:
                return p
        return None

    @discord.ui.button(label="🏆  Confirmar Presença", style=discord.ButtonStyle.success, custom_id="confirmar_partida_campeonato")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        membro     = interaction.user
        ids_cargos = {r.id for r in membro.roles}

        if not any(rid in ids_cargos for rid in self.rank_ids_extras):
            await interaction.response.send_message(
                f"❌ Apenas jogadores **{self.rank_alvo}** podem confirmar presença nesta partida.",
                ephemeral=True
            )
            return

        partidas = ler("partidas_campeonato")
        partida = self._buscar_partida(partidas)
        if partida is None:
            await interaction.response.send_message("⚠️ Não achei os dados dessa partida — fala com um admin.", ephemeral=True)
            return

        if membro.id in partida["confirmados"]:
            await interaction.response.send_message("⚠️ Você já confirmou presença nesta partida!", ephemeral=True)
            return

        partida["confirmados"].append(membro.id)
        salvar("partidas_campeonato", partidas)

        await _atualizar_embed_confirmados(interaction.message, interaction.guild, partida["confirmados"])

        canal_partida = interaction.client.get_channel(self.canal_partida_id)
        if canal_partida:
            await canal_partida.set_permissions(
                membro, view_channel=True, send_messages=True, read_message_history=True
            )
            await canal_partida.send(f"✅ {membro.mention} confirmou presença!")

        canal_voz_id = partida.get("canal_voz_id")
        if canal_voz_id:
            canal_voz = interaction.client.get_channel(canal_voz_id)
            if canal_voz:
                try:
                    await canal_voz.set_permissions(membro, view_channel=True, connect=True, speak=True)
                except discord.HTTPException as e:
                    print(f"[PARTIDA-CAMPEONATO] ⚠️ Erro ao liberar canal de voz pra {membro}: {e}")

        await interaction.response.send_message(
            f"✅ Presença confirmada! Você agora tem acesso a {canal_partida.mention if canal_partida else 'o canal da partida'}. 🚀",
            ephemeral=True
        )
        print(f"[PARTIDA-CAMPEONATO] ✅ {membro} confirmou presença.")


async def criar_partida_campeonato(
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

    nome_canal = "campeonato-" + "".join(c if c.isalnum() or c == "-" else "-" for c in adversario.lower().strip())
    nome_canal = nome_canal[:50]

    canal_anuncio = guild.get_channel(CAMPEONATO_PARTIDAS_CHANNEL_ID) if CAMPEONATO_PARTIDAS_CHANNEL_ID else interaction.channel
    if canal_anuncio is None:
        await interaction.response.send_message("❌ Canal de partidas de campeonato não encontrado.", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for admin_role_id in ADMIN_ROLE_IDS:
        admin_role = guild.get_role(admin_role_id)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    overwrites_voz = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
        guild.me:           discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
    }
    for admin_role_id in ADMIN_ROLE_IDS:
        admin_role = guild.get_role(admin_role_id)
        if admin_role:
            overwrites_voz[admin_role] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

    categoria = canal_anuncio.category if isinstance(canal_anuncio, discord.TextChannel) else None
    canal_partida = await guild.create_text_channel(
        name=nome_canal, overwrites=overwrites, category=categoria,
        reason=f"Partida de campeonato vs {adversario} criada por {interaction.user}"
    )

    categoria_voz_id = CATEGORIA_VOZ_CAMPEONATO_ID or CATEGORIA_VOZ_AMISTOSOS_ID
    categoria_voz  = guild.get_channel(categoria_voz_id)
    nome_canal_voz = f"🏆│Campeonato {adversario}"[:100]
    canal_voz = await guild.create_voice_channel(
        name=nome_canal_voz, overwrites=overwrites_voz, category=categoria_voz,
        reason=f"Canal de voz da partida de campeonato vs {adversario} criado por {interaction.user}"
    )

    embed = discord.Embed(title="🏆 ⋆｡°✩  PARTIDA DE CAMPEONATO  ✩°｡⋆ 🏆", color=COR_CAMPEONATO)
    embed.add_field(name="\u200b", value="```『 F I C H A   D A   P A R T I D A 』```", inline=False)
    embed.add_field(name="⚔️  Adversário",   value=f"**{adversario}**", inline=True)
    embed.add_field(name="🗓️  Data / Hora",  value=f"**{data_hora}**",  inline=True)
    embed.add_field(name="🎖️  Rank",         value=rank_display,        inline=True)
    if info_extra:
        embed.add_field(name="🗒️  Informações", value=info_extra, inline=False)
    embed.add_field(
        name="\u200b",
        value=(
            f"📣 {mencao_str} — Confirme sua presença abaixo!\n"
            f"📁 Canal da partida: {canal_partida.mention}\n"
            f"🔊 Canal de voz: {canal_voz.mention}"
        ),
        inline=False
    )
    embed.set_footer(text=f"🏆 Campeonato oficial · Anunciado por {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    view_conf   = ConfirmarPresencaCampeonatoView(rank_alvo=rank_salvo, rank_id=ranks_ids[0], canal_partida_id=canal_partida.id, rank_ids_extras=ranks_ids)
    msg_anuncio = await canal_anuncio.send(content=mencao_str, embed=embed, view=view_conf)

    cog = interaction.client.cogs.get("CampeonatoPartida")
    if cog:
        cog.registrar(msg_anuncio.id, canal_partida.id, canal_voz.id)

    partidas = ler("partidas_campeonato")
    data_hora_ts = _parse_data_hora(data_hora)
    partidas.append({
        "id": len(partidas) + 1, "adversario": adversario, "data": data_hora,
        "rank": rank_salvo, "resultado": None, "placar": "", "confirmados": [],
        "canal_id": canal_partida.id, "canal_voz_id": canal_voz.id, "criado_em": agora_str(),
        "msg_anuncio_id": msg_anuncio.id,
        "canal_anuncio_id": canal_anuncio.id,
        "rank_id": ranks_ids[0],
        "rank_ids_extras": ranks_ids,
        "data_hora_ts": data_hora_ts,
        "lembretes_enviados": [],
    })
    salvar("partidas_campeonato", partidas)

    embed_canal = discord.Embed(
        title=f"🏆 Campeonato — vs {adversario}",
        description=(
            f"Bem-vindos ao canal oficial da partida de campeonato! ⚔️\n\n"
            f"**🎖️ Rank:** {rank_display}\n"
            f"**🗓️ Data:** {data_hora}\n"
            f"**🔊 Voz:** {canal_voz.mention}\n"
            + (f"**🗒️ Info:** {info_extra}\n" if info_extra else "") +
            "\nSe quiser desistir, clique no botão abaixo."
        ),
        color=COR_CAMPEONATO
    )
    await canal_partida.send(embed=embed_canal, view=SairPartidaCampeonatoView())
    await canal_partida.send(f"🔊 Canal de voz da partida: {canal_voz.mention}")

    if data_hora_ts is None:
        aviso_lembretes = (
            "\n⚠️ Não consegui reconhecer a data/horário pra agendar os lembretes automáticos "
            "(use algo tipo `15/06 às 20h00`). A partida foi criada normalmente, só sem os avisos automáticos."
        )
    else:
        aviso_lembretes = ""

    await interaction.response.send_message(
        f"🏆 Partida de campeonato anunciada! Canal criado: {canal_partida.mention}{aviso_lembretes}", ephemeral=True
    )
    print(f"[PARTIDA-CAMPEONATO] ✅ {interaction.user} anunciou partida de campeonato vs {adversario} — {rank_salvo}")


class CampeonatoPartida(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.partida_map: dict[int, tuple[int, int | None]] = {}

        self.bot.add_view(SairPartidaCampeonatoView())

        for p in ler("partidas_campeonato"):
            if p.get("resultado") is not None:
                continue

            msg_id       = p.get("msg_anuncio_id")
            canal_id     = p.get("canal_id")
            canal_voz_id = p.get("canal_voz_id")
            rank_id      = p.get("rank_id")
            if msg_id is None or canal_id is None:
                continue

            view = ConfirmarPresencaCampeonatoView(
                rank_alvo=p.get("rank", ""),
                rank_id=rank_id,
                canal_partida_id=canal_id,
                rank_ids_extras=p.get("rank_ids_extras") or ([rank_id] if rank_id else []),
            )
            self.bot.add_view(view, message_id=msg_id)
            self.partida_map[msg_id] = (canal_id, canal_voz_id)

        self.lembretes_partida_campeonato.start()

    def cog_unload(self):
        self.lembretes_partida_campeonato.cancel()

    def registrar(self, message_id: int, canal_id: int, canal_voz_id: int | None = None):
        self.partida_map[message_id] = (canal_id, canal_voz_id)

    @tasks.loop(minutes=1)
    async def lembretes_partida_campeonato(self):
        await self.bot.wait_until_ready()
        agora_ts = time.time()
        partidas = ler("partidas_campeonato")
        mudou = False

        for partida in partidas:
            if partida.get("resultado") is not None:
                continue

            ts = partida.get("data_hora_ts")
            if not ts or agora_ts >= ts:
                continue

            confirmados = partida.get("confirmados") or []
            if not confirmados:
                continue

            enviados = partida.setdefault("lembretes_enviados", [])

            for segundos, chave, destino in _MARCOS_LEMBRETE:
                if chave in enviados:
                    continue

                tempo_restante = ts - agora_ts
                if tempo_restante > segundos:
                    continue

                if tempo_restante < segundos - (15 * 60):
                    enviados.append(chave)
                    mudou = True
                    continue

                await self._enviar_lembrete(partida, destino, chave)
                enviados.append(chave)
                mudou = True

        if mudou:
            salvar("partidas_campeonato", partidas)

    @lembretes_partida_campeonato.before_loop
    async def antes_lembretes_partida_campeonato(self):
        await self.bot.wait_until_ready()

    async def _enviar_lembrete(self, partida: dict, destino: str, chave: str):
        tempo_texto = _TEXTO_TEMPO.get(chave, "pouco tempo")
        adversario  = partida.get("adversario", "adversário")
        data_hora   = partida.get("data", "")
        confirmados = partida.get("confirmados") or []
        canal_id    = partida.get("canal_id")

        if destino in ("canal", "ambos"):
            canal = self.bot.get_channel(canal_id) if canal_id else None
            if canal is not None:
                mencoes = " ".join(f"<@{uid}>" for uid in confirmados)
                try:
                    await canal.send(
                        f"⏰ **Faltam {tempo_texto} pra partida de campeonato vs {adversario}!** ({data_hora})\n{mencoes}"
                        f"{_AVISO_SAIR_CANAL}",
                        view=SairPartidaCampeonatoView(),
                    )
                except discord.HTTPException as e:
                    print(f"[PARTIDA-CAMPEONATO] ⚠️ Erro ao mandar lembrete no canal: {e}")

        if destino in ("dm", "ambos"):
            for uid in confirmados:
                usuario = self.bot.get_user(uid)
                if usuario is None:
                    try:
                        usuario = await self.bot.fetch_user(uid)
                    except discord.HTTPException:
                        continue
                try:
                    await usuario.send(
                        f"⏰ **Faltam {tempo_texto} pra sua partida de campeonato vs {adversario}!** ({data_hora})\n"
                        f"Não esquece de aparecer! 🚀"
                        f"{_AVISO_SAIR_DM}"
                    )
                except discord.Forbidden:
                    pass
                except discord.HTTPException as e:
                    print(f"[PARTIDA-CAMPEONATO] ⚠️ Erro ao mandar lembrete por DM pra {uid}: {e}")

    async def _mover_membros_pos_partida(self, canal_voz: discord.VoiceChannel):
        await mu.mover_membros_pos_amistoso(self.bot, canal_voz)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        info = self.partida_map.pop(message.id, None)
        if info is None:
            return
        canal_id, canal_voz_id = info

        canal = self.bot.get_channel(canal_id)
        if canal:
            await canal.delete(reason="Mensagem da partida de campeonato deletada — canal removido automaticamente.")
            print(f"[PARTIDA-CAMPEONATO] 🗑️ Canal {canal.name} deletado junto com o anúncio.")

        if canal_voz_id:
            canal_voz = self.bot.get_channel(canal_voz_id)
            if canal_voz:
                await self._mover_membros_pos_partida(canal_voz)
                await canal_voz.delete(reason="Mensagem da partida de campeonato deletada — canal de voz removido automaticamente.")
                print(f"[PARTIDA-CAMPEONATO] 🗑️ Canal de voz {canal_voz.name} deletado junto com o anúncio.")

    @app_commands.command(name="partida-campeonato", description="Anuncia uma partida de campeonato (formato igual ao /amistoso).")
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
    @app_commands.describe(
        adversario="Nome do time adversário",
        data_hora="Data e horário (ex: 15/06 às 20h00)",
        rank1="Cargo do rank principal",
        rank2="Segundo cargo de rank (opcional)",
        info_extra="Informações extras (opcional)",
    )
    async def partida_campeonato(
        self,
        interaction: discord.Interaction,
        adversario: str,
        data_hora: str,
        rank1: discord.Role,
        rank2: discord.Role = None,
        info_extra: str = "",
    ):
        await criar_partida_campeonato(interaction, adversario, data_hora, rank1, info_extra, rank2)

    @partida_campeonato.error
    async def partida_campeonato_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("❌ Apenas **Administradores** podem anunciar partidas de campeonato.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CampeonatoPartida(bot))
