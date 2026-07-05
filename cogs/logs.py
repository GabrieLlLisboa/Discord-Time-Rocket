from __future__ import annotations

import discord
from discord.ext import commands
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Sistema de Logs
#  Arquivo: cogs/logs.py
#
#  Registra praticamente tudo que acontece no servidor num único
#  canal de logs: entradas/saídas, moderação (kick/ban/timeout),
#  mensagens apagadas/editadas (com quem apagou), canais, cargos,
#  emojis, figurinhas, threads, canais de voz, convites, mudanças
#  de nome/avatar de usuário e alterações gerais do servidor.
#
#  A maioria dos eventos do Discord não informa quem fez a ação
#  diretamente — por isso usamos o Audit Log do servidor pra achar
#  o responsável, sempre casando a entrada mais recente (dentro de
#  uma janela curta de tempo) com o alvo do evento.
# ─────────────────────────────────────────────

LOG_CHANNEL_ID = 1521897698419019907

# ── Cores por categoria de evento ────────────────────────────────────────────
COR_ENTRADA   = 0x57F287  # verde
COR_SAIDA     = 0x99AAB5  # cinza
COR_MODERACAO = 0xED4245  # vermelho
COR_EDICAO    = 0xFEE75C  # amarelo
COR_EXCLUSAO  = 0xED4245  # vermelho
COR_CRIACAO   = 0x57F287  # verde
COR_CARGO     = 0xEB459E  # rosa
COR_SERVIDOR  = 0x5865F2  # azul blurple
COR_CONVITE   = 0x5865F2  # azul blurple
COR_VOZ       = 0x5865F2  # azul blurple
COR_THREAD    = 0x57F287  # verde
COR_USUARIO   = 0xFEE75C  # amarelo

# Janela de tempo (em segundos) pra considerar uma entrada do audit log
# como sendo "a responsável" pelo evento que acabamos de receber.
JANELA_AUDITORIA_SEGUNDOS = 10


def _quem(executor: discord.abc.User | None) -> str:
    """Formata o executor de uma ação pra exibir no log, ou 'Desconhecido'."""
    return f"{executor.mention} (`{executor}`)" if executor else "Desconhecido"


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Helper central: manda um embed no canal de logs ─────────────────────
    async def log(self, title: str, description: str = "", color: int = COR_SERVIDOR,
                   fields: list | None = None, thumbnail: str | None = None):
        canal = self.bot.get_channel(LOG_CHANNEL_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(LOG_CHANNEL_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                print(f"[LOGS] ⚠️ Canal de logs ({LOG_CHANNEL_ID}) não encontrado.")
                return

        embed = discord.Embed(
            title=title,
            description=description[:4096] if description else None,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        for nome, valor in (fields or []):
            if valor is None:
                continue
            texto = str(valor).strip()
            embed.add_field(name=nome, value=texto[:1024] if texto else "—", inline=False)
        embed.set_footer(text="Sistema de Logs")

        try:
            await canal.send(embed=embed)
        except discord.Forbidden:
            print("[LOGS] ⚠️ Sem permissão pra mandar mensagem no canal de logs.")
        except discord.HTTPException as e:
            print(f"[LOGS] ⚠️ Falha ao mandar log: {e}")

    # ── Helper: procura no audit log quem fez uma ação recente ──────────────
    async def _executor(self, guild: discord.Guild | None, action: discord.AuditLogAction,
                         target_id: int | None = None):
        """Retorna (executor, motivo) da entrada mais recente do audit log que bate
        com a ação (e o alvo, se informado), desde que tenha acontecido há poucos
        segundos. Se não achar nada compatível, retorna (None, None)."""
        if guild is None:
            return None, None
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                delta = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                if delta > JANELA_AUDITORIA_SEGUNDOS:
                    break  # entradas vêm da mais recente pra mais antiga — pode parar de procurar
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                return entry.user, entry.reason
        except discord.Forbidden:
            print("[LOGS] ⚠️ Sem permissão pra ler o Audit Log (é necessário 'Ver Registro de Auditoria').")
        except discord.HTTPException:
            pass
        return None, None

    # ═════════════════════════ ENTRADA / SAÍDA DE MEMBROS ═══════════════════

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.log(
            title="📥 Membro entrou no servidor",
            description=f"{member.mention} entrou no servidor.",
            color=COR_ENTRADA,
            fields=[
                ("Usuário", f"`{member}` (`{member.id}`)"),
                ("Conta criada em", discord.utils.format_dt(member.created_at, style="F")),
            ],
            thumbnail=member.display_avatar.url,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        executor, motivo = await self._executor(member.guild, discord.AuditLogAction.kick, target_id=member.id)
        if executor:
            await self.log(
                title="👢 Membro expulso",
                description=f"{member.mention} foi expulso do servidor.",
                color=COR_MODERACAO,
                fields=[
                    ("Usuário", f"`{member}` (`{member.id}`)"),
                    ("Expulso por", _quem(executor)),
                    ("Motivo", motivo or "Nenhum motivo informado"),
                ],
                thumbnail=member.display_avatar.url,
            )
        else:
            await self.log(
                title="📤 Membro saiu do servidor",
                description=f"{member.mention} saiu do servidor.",
                color=COR_SAIDA,
                fields=[("Usuário", f"`{member}` (`{member.id}`)")],
                thumbnail=member.display_avatar.url,
            )

    # ═════════════════════════ BAN / UNBAN ═══════════════════════════════════

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        executor, motivo = await self._executor(guild, discord.AuditLogAction.ban, target_id=user.id)
        await self.log(
            title="🔨 Membro banido",
            description=f"{user.mention} foi banido do servidor.",
            color=COR_MODERACAO,
            fields=[
                ("Usuário", f"`{user}` (`{user.id}`)"),
                ("Banido por", _quem(executor)),
                ("Motivo", motivo or "Nenhum motivo informado"),
            ],
            thumbnail=user.display_avatar.url,
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        executor, motivo = await self._executor(guild, discord.AuditLogAction.unban, target_id=user.id)
        await self.log(
            title="🕊️ Membro desbanido",
            description=f"{user.mention} foi desbanido do servidor.",
            color=COR_ENTRADA,
            fields=[
                ("Usuário", f"`{user}` (`{user.id}`)"),
                ("Desbanido por", _quem(executor)),
                ("Motivo", motivo or "Nenhum motivo informado"),
            ],
            thumbnail=user.display_avatar.url,
        )

    # ═════════════════════════ MENSAGENS ═════════════════════════════════════

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return

        # ── Alguém tentou apagar uma mensagem de log? Denuncia e reenvia ────
        if message.channel.id == LOG_CHANNEL_ID and message.author.id == self.bot.user.id:
            executor, _ = await self._executor(message.guild, discord.AuditLogAction.message_delete, target_id=message.author.id)
            aviso = (
                f"🚨 {executor.mention} tentou apagar uma log!"
                if executor else
                "🚨 Alguém tentou apagar uma log, mas não consegui identificar quem "
                "(dá uma olhada se o bot tem permissão de **Ver Registro de Auditoria**)."
            )
            try:
                await message.channel.send(aviso)
            except discord.Forbidden:
                print("[LOGS] ⚠️ Sem permissão pra avisar sobre tentativa de apagar log.")

            if message.embeds:
                try:
                    await message.channel.send(embed=message.embeds[0])
                except discord.Forbidden:
                    print("[LOGS] ⚠️ Sem permissão pra reenviar a log apagada.")
            return  # não precisa cair no log genérico de "mensagem apagada" abaixo

        conteudo = message.content or "*(sem texto — anexo, embed ou imagem)*"

        # Tenta descobrir se foi um moderador quem apagou (senão, foi o próprio autor).
        executor, _ = await self._executor(message.guild, discord.AuditLogAction.message_delete, target_id=message.author.id)
        quem_apagou = _quem(executor) if executor and executor.id != message.author.id else "O(a) próprio(a) autor(a)"

        campos = [
            ("Autor", f"`{message.author}` (`{message.author.id}`)"),
            ("Canal", message.channel.mention),
            ("Apagada por", quem_apagou),
            ("Conteúdo", conteudo),
        ]
        if message.attachments:
            campos.append(("Anexos", "\n".join(a.url for a in message.attachments)))

        await self.log(
            title="🗑️ Mensagem apagada",
            description=f"Uma mensagem de {message.author.mention} foi apagada em {message.channel.mention}.",
            color=COR_EXCLUSAO,
            fields=campos,
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list):
        if not messages or messages[0].guild is None:
            return
        canal = messages[0].channel

        # ── Apagaram um monte de logs de uma vez? Denuncia e reenvia tudo ───
        if canal.id == LOG_CHANNEL_ID:
            logs_do_bot = [m for m in messages if m.author.id == self.bot.user.id and m.embeds]
            if logs_do_bot:
                executor, _ = await self._executor(messages[0].guild, discord.AuditLogAction.message_bulk_delete, target_id=canal.id)
                aviso = (
                    f"🚨 {executor.mention} tentou apagar **{len(logs_do_bot)}** log(s) de uma vez!"
                    if executor else
                    f"🚨 Alguém tentou apagar **{len(logs_do_bot)}** log(s) de uma vez, mas não consegui "
                    "identificar quem (dá uma olhada se o bot tem permissão de **Ver Registro de Auditoria**)."
                )
                try:
                    await canal.send(aviso)
                    for m in sorted(logs_do_bot, key=lambda x: x.created_at):
                        await canal.send(embed=m.embeds[0])
                except discord.Forbidden:
                    print("[LOGS] ⚠️ Sem permissão pra avisar/reenviar logs apagadas em massa.")
                return  # não precisa do log genérico de "apagadas em massa" abaixo

        executor, _ = await self._executor(messages[0].guild, discord.AuditLogAction.message_bulk_delete, target_id=canal.id)
        await self.log(
            title="🧹 Mensagens apagadas em massa",
            description=f"**{len(messages)}** mensagens foram apagadas de uma vez em {canal.mention}.",
            color=COR_EXCLUSAO,
            fields=[
                ("Canal", canal.mention),
                ("Quantidade", str(len(messages))),
                ("Apagadas por", _quem(executor)),
            ],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.content == after.content:
            return  # sem guild (DM) ou nenhuma mudança real de texto (ex: só um embed carregou)
        await self.log(
            title="✏️ Mensagem editada",
            description=(
                f"{before.author.mention} editou uma mensagem em {before.channel.mention}. "
                f"[Ir para a mensagem]({after.jump_url})"
            ),
            color=COR_EDICAO,
            fields=[
                ("Autor", f"`{before.author}` (`{before.author.id}`)"),
                ("Canal", before.channel.mention),
                ("Antes", before.content or "*(vazio)*"),
                ("Depois", after.content or "*(vazio)*"),
            ],
        )

    # ═════════════════════════ CANAIS ═════════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        executor, _ = await self._executor(channel.guild, discord.AuditLogAction.channel_create, target_id=channel.id)
        await self.log(
            title="📁 Canal criado",
            description=f"O canal **#{channel.name}** foi criado.",
            color=COR_CRIACAO,
            fields=[
                ("Tipo", str(channel.type).replace("_", " ").title()),
                ("ID", str(channel.id)),
                ("Criado por", _quem(executor)),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        executor, _ = await self._executor(channel.guild, discord.AuditLogAction.channel_delete)
        await self.log(
            title="🗑️ Canal excluído",
            description=f"O canal **#{channel.name}** foi excluído.",
            color=COR_EXCLUSAO,
            fields=[
                ("Tipo", str(channel.type).replace("_", " ").title()),
                ("ID", str(channel.id)),
                ("Excluído por", _quem(executor)),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        mudancas = []
        if before.name != after.name:
            mudancas.append(("Nome", f"`{before.name}` → `{after.name}`"))
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            mudancas.append(("Tópico", f"`{before.topic or '—'}` → `{after.topic or '—'}`"))
        if getattr(before, "category", None) != getattr(after, "category", None):
            antes = before.category.name if before.category else "Nenhuma"
            depois = after.category.name if after.category else "Nenhuma"
            mudancas.append(("Categoria", f"`{antes}` → `{depois}`"))
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            mudancas.append(("Modo lento", f"`{before.slowmode_delay}s` → `{after.slowmode_delay}s`"))
        if before.overwrites != after.overwrites:
            mudancas.append(("Permissões", "As permissões do canal foram alteradas."))

        if not mudancas:
            return  # mudança irrelevante pro log (ex: posição na lista de canais)

        executor, _ = await self._executor(after.guild, discord.AuditLogAction.channel_update, target_id=after.id)
        await self.log(
            title="⚙️ Canal editado",
            description=f"O canal {after.mention} foi editado.",
            color=COR_EDICAO,
            fields=[*mudancas, ("Editado por", _quem(executor))],
        )

    # ═════════════════════════ CARGOS ═════════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        executor, _ = await self._executor(role.guild, discord.AuditLogAction.role_create, target_id=role.id)
        await self.log(
            title="🎭 Cargo criado",
            description=f"O cargo **{role.name}** foi criado.",
            color=COR_CRIACAO,
            fields=[("ID", str(role.id)), ("Criado por", _quem(executor))],
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        executor, _ = await self._executor(role.guild, discord.AuditLogAction.role_delete)
        await self.log(
            title="🗑️ Cargo excluído",
            description=f"O cargo **{role.name}** foi excluído.",
            color=COR_EXCLUSAO,
            fields=[("ID", str(role.id)), ("Excluído por", _quem(executor))],
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        mudancas = []
        if before.name != after.name:
            mudancas.append(("Nome", f"`{before.name}` → `{after.name}`"))
        if before.color != after.color:
            mudancas.append(("Cor", f"`{before.color}` → `{after.color}`"))
        if before.hoist != after.hoist:
            mudancas.append(("Exibir separado", f"`{before.hoist}` → `{after.hoist}`"))
        if before.mentionable != after.mentionable:
            mudancas.append(("Mencionável", f"`{before.mentionable}` → `{after.mentionable}`"))
        if before.permissions != after.permissions:
            mudancas.append(("Permissões", "As permissões do cargo foram alteradas."))

        if not mudancas:
            return  # mudança irrelevante (ex: só a posição na lista mudou)

        executor, _ = await self._executor(after.guild, discord.AuditLogAction.role_update, target_id=after.id)
        await self.log(
            title="🎭 Cargo editado",
            description=f"O cargo **{after.name}** foi editado.",
            color=COR_EDICAO,
            fields=[*mudancas, ("Editado por", _quem(executor))],
        )

    # ═════════════════════════ MEMBROS: APELIDO, CARGOS E TIMEOUT ═════════════

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild

        # ── Apelido ──
        if before.nick != after.nick:
            executor, _ = await self._executor(guild, discord.AuditLogAction.member_update, target_id=after.id)
            await self.log(
                title="📝 Apelido alterado",
                description=f"O apelido de {after.mention} foi alterado.",
                color=COR_EDICAO,
                fields=[
                    ("Antes", before.nick or before.name),
                    ("Depois", after.nick or after.name),
                    ("Alterado por", _quem(executor) if executor else "O(a) próprio(a) usuário(a)"),
                ],
            )

        # ── Cargos ──
        cargos_antes = set(before.roles)
        cargos_depois = set(after.roles)
        if cargos_antes != cargos_depois:
            adicionados = cargos_depois - cargos_antes
            removidos = cargos_antes - cargos_depois
            executor, _ = await self._executor(guild, discord.AuditLogAction.member_role_update, target_id=after.id)

            campos = []
            if adicionados:
                campos.append(("Cargos adicionados", ", ".join(r.mention for r in adicionados)))
            if removidos:
                campos.append(("Cargos removidos", ", ".join(r.mention for r in removidos)))
            campos.append(("Alterado por", _quem(executor)))

            await self.log(
                title="🏷️ Cargos do membro alterados",
                description=f"Os cargos de {after.mention} (`{after}`) foram alterados.",
                color=COR_CARGO,
                fields=campos,
            )

        # ── Timeout ──
        if before.timed_out_until != after.timed_out_until:
            executor, motivo = await self._executor(guild, discord.AuditLogAction.member_update, target_id=after.id)
            aplicado = after.timed_out_until is not None and after.timed_out_until > datetime.now(timezone.utc)
            if aplicado:
                await self.log(
                    title="🔇 Timeout aplicado",
                    description=f"{after.mention} (`{after}`) recebeu um timeout.",
                    color=COR_MODERACAO,
                    fields=[
                        ("Expira em", discord.utils.format_dt(after.timed_out_until, style="F")),
                        ("Aplicado por", _quem(executor)),
                        ("Motivo", motivo or "Nenhum motivo informado"),
                    ],
                )
            else:
                await self.log(
                    title="🔊 Timeout removido",
                    description=f"O timeout de {after.mention} (`{after}`) foi removido.",
                    color=COR_ENTRADA,
                    fields=[("Removido por", _quem(executor))],
                )

    # ═════════════════════════ EMOJIS ═════════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: list, after: list):
        ids_antes = {e.id for e in before}
        ids_depois = {e.id for e in after}
        mapa_antes = {e.id: e for e in before}

        for emoji in after:
            if emoji.id not in ids_antes:
                executor, _ = await self._executor(guild, discord.AuditLogAction.emoji_create, target_id=emoji.id)
                await self.log(
                    title="😀 Emoji criado",
                    description=f"O emoji **{emoji.name}** foi criado. {emoji}",
                    color=COR_CRIACAO,
                    fields=[("Criado por", _quem(executor))],
                )
                continue

            anterior = mapa_antes.get(emoji.id)
            if anterior and anterior.name != emoji.name:
                executor, _ = await self._executor(guild, discord.AuditLogAction.emoji_update, target_id=emoji.id)
                await self.log(
                    title="✏️ Emoji editado",
                    description=f"Um emoji foi renomeado. {emoji}",
                    color=COR_EDICAO,
                    fields=[
                        ("Antes", anterior.name),
                        ("Depois", emoji.name),
                        ("Editado por", _quem(executor)),
                    ],
                )

        for emoji in before:
            if emoji.id not in ids_depois:
                executor, _ = await self._executor(guild, discord.AuditLogAction.emoji_delete)
                await self.log(
                    title="🗑️ Emoji excluído",
                    description=f"O emoji **{emoji.name}** foi excluído.",
                    color=COR_EXCLUSAO,
                    fields=[("Excluído por", _quem(executor))],
                )

    # ═════════════════════════ SERVIDOR ═══════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        mudancas = []
        if before.name != after.name:
            mudancas.append(("Nome", f"`{before.name}` → `{after.name}`"))
        if before.icon != after.icon:
            mudancas.append(("Ícone", "O ícone do servidor foi alterado."))
        if before.banner != after.banner:
            mudancas.append(("Banner", "O banner do servidor foi alterado."))
        if before.owner_id != after.owner_id:
            mudancas.append(("Dono do servidor", f"`{before.owner_id}` → `{after.owner_id}`"))
        if before.verification_level != after.verification_level:
            mudancas.append(("Nível de verificação", f"`{before.verification_level}` → `{after.verification_level}`"))

        if not mudancas:
            return

        executor, _ = await self._executor(after, discord.AuditLogAction.guild_update, target_id=after.id)
        await self.log(
            title="🏰 Servidor atualizado",
            description="As configurações do servidor foram alteradas.",
            color=COR_SERVIDOR,
            fields=[*mudancas, ("Alterado por", _quem(executor))],
            thumbnail=after.icon.url if after.icon else None,
        )

    # ═════════════════════════ CONVITES ═══════════════════════════════════════

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        criador = invite.inviter
        await self.log(
            title="🔗 Convite criado",
            description=f"Um novo convite foi criado para {invite.channel.mention if invite.channel else 'um canal'}.",
            color=COR_CONVITE,
            fields=[
                ("Código", f"`{invite.code}`"),
                ("Criado por", _quem(criador)),
                ("Expira em", discord.utils.format_dt(invite.expires_at, style="F") if invite.expires_at else "Nunca"),
                ("Usos máximos", str(invite.max_uses) if invite.max_uses else "Ilimitado"),
            ],
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await self.log(
            title="🗑️ Convite excluído",
            description=f"O convite `{invite.code}` foi excluído ou expirou.",
            color=COR_EXCLUSAO,
            fields=[("Canal", invite.channel.mention if invite.channel else "Desconhecido")],
        )


    # ═════════════════════════ STICKERS ════════════════════════════════════════

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before: list, after: list):
        ids_antes = {s.id for s in before}
        ids_depois = {s.id for s in after}
        mapa_antes = {s.id: s for s in before}

        for sticker in after:
            if sticker.id not in ids_antes:
                executor, _ = await self._executor(guild, discord.AuditLogAction.sticker_create, target_id=sticker.id)
                await self.log(
                    title="🏷️ Figurinha criada",
                    description=f"A figurinha **{sticker.name}** foi criada.",
                    color=COR_CRIACAO,
                    fields=[("Criada por", _quem(executor))],
                    thumbnail=sticker.url,
                )
                continue

            anterior = mapa_antes.get(sticker.id)
            if anterior and anterior.name != sticker.name:
                executor, _ = await self._executor(guild, discord.AuditLogAction.sticker_update, target_id=sticker.id)
                await self.log(
                    title="✏️ Figurinha editada",
                    description="Uma figurinha foi renomeada.",
                    color=COR_EDICAO,
                    fields=[
                        ("Antes", anterior.name),
                        ("Depois", sticker.name),
                        ("Editada por", _quem(executor)),
                    ],
                )

        for sticker in before:
            if sticker.id not in ids_depois:
                executor, _ = await self._executor(guild, discord.AuditLogAction.sticker_delete)
                await self.log(
                    title="🗑️ Figurinha excluída",
                    description=f"A figurinha **{sticker.name}** foi excluída.",
                    color=COR_EXCLUSAO,
                    fields=[("Excluída por", _quem(executor))],
                )

    # ═════════════════════════ THREADS ═════════════════════════════════════════

    @commands.Cog.listener()
    async def on_thread_join(self, thread: discord.Thread):
        # on_thread_join dispara tanto quando alguém cria quanto quando o bot entra
        # numa thread já existente — usamos o audit log pra distinguir uma criação real.
        executor, _ = await self._executor(thread.guild, discord.AuditLogAction.thread_create, target_id=thread.id)
        if executor is None:
            return
        await self.log(
            title="🧵 Thread criada",
            description=f"A thread **{thread.name}** foi criada em {thread.parent.mention if thread.parent else 'um canal'}.",
            color=COR_THREAD,
            fields=[("Criada por", _quem(executor))],
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        executor, _ = await self._executor(thread.guild, discord.AuditLogAction.thread_delete)
        await self.log(
            title="🗑️ Thread excluída",
            description=f"A thread **{thread.name}** foi excluída.",
            color=COR_EXCLUSAO,
            fields=[("Excluída por", _quem(executor))],
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        mudancas = []
        if before.name != after.name:
            mudancas.append(("Nome", f"`{before.name}` → `{after.name}`"))
        if before.archived != after.archived:
            mudancas.append(("Arquivada", f"`{before.archived}` → `{after.archived}`"))
        if before.locked != after.locked:
            mudancas.append(("Trancada", f"`{before.locked}` → `{after.locked}`"))

        if not mudancas:
            return

        executor, _ = await self._executor(after.guild, discord.AuditLogAction.thread_update, target_id=after.id)
        await self.log(
            title="🧵 Thread editada",
            description=f"A thread **{after.name}** foi editada.",
            color=COR_EDICAO,
            fields=[*mudancas, ("Editada por", _quem(executor))],
        )

    # ═════════════════════════ CANAIS DE VOZ ═══════════════════════════════════

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # ── Entrou em um canal de voz ──
        if before.channel is None and after.channel is not None:
            await self.log(
                title="🔊 Entrou em canal de voz",
                description=f"{member.mention} entrou no canal de voz {after.channel.mention}.",
                color=COR_VOZ,
                fields=[("Usuário", f"`{member}` (`{member.id}`)")],
            )

        # ── Saiu de um canal de voz ──
        elif before.channel is not None and after.channel is None:
            await self.log(
                title="🔇 Saiu de canal de voz",
                description=f"{member.mention} saiu do canal de voz {before.channel.mention}.",
                color=COR_VOZ,
                fields=[("Usuário", f"`{member}` (`{member.id}`)")],
            )

        # ── Trocou de canal de voz ──
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            executor, _ = await self._executor(member.guild, discord.AuditLogAction.member_move, target_id=member.id)
            await self.log(
                title="🔀 Trocou de canal de voz",
                description=f"{member.mention} foi movido(a) de canal de voz.",
                color=COR_VOZ,
                fields=[
                    ("De", before.channel.mention),
                    ("Para", after.channel.mention),
                    ("Usuário", f"`{member}` (`{member.id}`)"),
                    ("Movido por", _quem(executor) if executor else "O(a) próprio(a) usuário(a)"),
                ],
            )

        # ── Mutado/desmutado ou ensurdecido/desensurdecido pelo servidor ──
        if before.mute != after.mute or before.deaf != after.deaf:
            executor, _ = await self._executor(member.guild, discord.AuditLogAction.member_update, target_id=member.id)
            mudancas = []
            if before.mute != after.mute:
                mudancas.append(("Mutado pelo servidor", f"`{before.mute}` → `{after.mute}`"))
            if before.deaf != after.deaf:
                mudancas.append(("Ensurdecido pelo servidor", f"`{before.deaf}` → `{after.deaf}`"))
            await self.log(
                title="🎚️ Estado de voz alterado",
                description=f"O estado de voz de {member.mention} foi alterado.",
                color=COR_VOZ,
                fields=[*mudancas, ("Alterado por", _quem(executor))],
            )

    # ═════════════════════════ USUÁRIO (NOME/AVATAR GLOBAL) ════════════════════

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # Evento global do Discord (não é por servidor) — filtramos só o que interessa.
        if before.name == after.name and before.discriminator == after.discriminator and before.avatar == after.avatar:
            return

        mudancas = []
        if before.name != after.name:
            mudancas.append(("Nome de usuário", f"`{before.name}` → `{after.name}`"))
        if before.discriminator != after.discriminator:
            mudancas.append(("Discriminador", f"`{before.discriminator}` → `{after.discriminator}`"))
        if before.avatar != after.avatar:
            mudancas.append(("Avatar", "O avatar do usuário foi alterado."))

        await self.log(
            title="👤 Perfil de usuário alterado",
            description=f"{after.mention} atualizou o perfil do Discord.",
            color=COR_USUARIO,
            fields=[*mudancas, ("Usuário", f"`{after}` (`{after.id}`)")],
            thumbnail=after.display_avatar.url,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
