from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

from cogs import mod_utils as mu

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Moderação
#  Arquivo: cogs/moderation.py
#
#  Todos os comandos de moderação em Slash Command:
#   warn, avisos, timeout, untimeout, kick, ban, tempban, unban, softban,
#   clear, slowmode, nick, lock, unlock, cargo (add/remove), canal
#   (criar/deletar/renomear), thread (trancar/destrancar/arquivar), historico
#
#  Todas as ações perigosas pedem confirmação (configurável) e tudo é
#  registrado no histórico de punições + no canal de logs de moderação.
# ─────────────────────────────────────────────────────────────────────────────


def _exige_confirmacao(guild_id: int) -> bool:
    return mu.get_config(guild_id).get("exigir_confirmacao", True)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.checar_temporarias.start()

    def cog_unload(self):
        self.checar_temporarias.cancel()

    # ── Loop: expira tempbans/timeouts vencidos automaticamente ─────────────
    @tasks.loop(minutes=1)
    async def checar_temporarias(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for registro in mu.punicoes_ativas_temporarias(guild.id):
                try:
                    expira = datetime.fromisoformat(registro["expira_em"])
                except (ValueError, TypeError):
                    continue
                if expira > datetime.now(timezone.utc):
                    continue
                if registro["tipo"] == "tempban":
                    try:
                        await guild.unban(discord.Object(id=registro["user_id"]), reason="Ban temporário expirado")
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                    mu.remover_punicao(guild.id, registro["id"])
                    embed = mu.embed_base("♻️ Ban temporário expirado",
                                           f"<@{registro['user_id']}> (`{registro['user_id']}`) foi desbanido automaticamente.",
                                           mu.COR_SUCESSO)
                    await mu.enviar_log_moderacao(self.bot, guild, embed)
                # timeouts expiram sozinhos pelo próprio Discord — só limpamos o registro
                elif registro["tipo"] == "timeout":
                    mu.remover_punicao(guild.id, registro["id"])

    @checar_temporarias.before_loop
    async def _antes(self):
        await self.bot.wait_until_ready()

    # ── /warn ─────────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Aplica uma advertência a um membro.")
    @app_commands.describe(membro="Membro a ser advertido", motivo="Motivo da advertência")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, membro.id, interaction.user.id, "warn", motivo)
        total = len(mu.avisos_usuario(interaction.guild_id, membro.id))

        embed = mu.embed_punicao("warn", membro, interaction.user, motivo, punicao_id=registro["id"])
        embed.add_field(name="Total de avisos ativos", value=str(total), inline=False)
        await interaction.response.send_message(embed=embed)

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            dm = mu.embed_base("⚠️ Você recebeu uma advertência",
                                f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}\n**Total de avisos:** {total}",
                                mu.COR_ALERTA)
            await mu.notificar_usuario(membro, dm)

        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /avisos ───────────────────────────────────────────────────────────
    @app_commands.command(name="avisos", description="Lista os avisos ativos de um membro.")
    @app_commands.describe(membro="Membro a consultar")
    @app_commands.default_permissions(moderate_members=True)
    async def avisos(self, interaction: discord.Interaction, membro: discord.Member):
        regs = mu.avisos_usuario(interaction.guild_id, membro.id)
        if not regs:
            return await interaction.response.send_message(
                embed=mu.embed_base("⚠️ Avisos", f"{membro.mention} não possui avisos ativos.", mu.COR_INFO),
                ephemeral=True,
            )
        desc = "\n".join(
            f"**#{r['id']}** — {r['motivo']} (por <@{r['moderador_id']}> em {r['criado_em'][:10]})"
            for r in regs
        )
        embed = mu.embed_base(f"⚠️ Avisos de {membro}", desc[:4096], mu.COR_ALERTA)
        embed.set_thumbnail(url=membro.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /removeraviso ─────────────────────────────────────────────────────
    @app_commands.command(name="removeraviso", description="Remove (invalida) um aviso pelo número do caso.")
    @app_commands.describe(caso_id="Número do caso (veja em /avisos ou /historico)")
    @app_commands.default_permissions(moderate_members=True)
    async def removeraviso(self, interaction: discord.Interaction, caso_id: int):
        ok = mu.remover_punicao(interaction.guild_id, caso_id)
        if ok:
            await interaction.response.send_message(embed=mu.embed_sucesso(f"Caso `#{caso_id}` removido/invalidado."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=mu.embed_erro(f"Caso `#{caso_id}` não encontrado."), ephemeral=True)

    # ── /historico-punicoes ──────────────────────────────────────────────
    @app_commands.command(name="historico-punicoes", description="Mostra o histórico completo de punições de um membro.")
    @app_commands.describe(membro="Membro a consultar")
    @app_commands.default_permissions(moderate_members=True)
    async def historico(self, interaction: discord.Interaction, membro: discord.Member):
        regs = mu.historico_usuario(interaction.guild_id, membro.id)
        if not regs:
            return await interaction.response.send_message(
                embed=mu.embed_base("📜 Histórico", f"{membro.mention} não possui histórico de punições.", mu.COR_INFO),
                ephemeral=True,
            )
        regs = sorted(regs, key=lambda r: r["criado_em"], reverse=True)[:20]
        linhas = []
        for r in regs:
            status = "✅ ativo" if r.get("ativo", True) else "▫️ inativo"
            emoji = mu.EMOJIS_TIPO.get(r["tipo"], "🛠️")
            linhas.append(f"{emoji} **#{r['id']} · {r['tipo']}** — {r['motivo']} · <@{r['moderador_id']}> · {status}")
        embed = mu.embed_base(f"📜 Histórico de {membro}", "\n".join(linhas)[:4096], mu.COR_NEUTRO)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=f"Mostrando os {len(regs)} casos mais recentes")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /timeout ──────────────────────────────────────────────────────────
    @app_commands.command(name="timeout", description="Aplica timeout (silenciar temporariamente) em um membro.")
    @app_commands.describe(membro="Membro", duracao="Ex: 10m, 1h, 1h30m, 7d (máx 28d)", motivo="Motivo")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, membro: discord.Member, duracao: str, motivo: str = "Não informado"):
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        segundos = mu.parsear_duracao(duracao)
        if not segundos or segundos > 28 * 86400:
            return await interaction.response.send_message(
                embed=mu.embed_erro("Duração inválida. Use algo como `10m`, `1h`, `1h30m`, `7d` (máximo 28 dias)."),
                ephemeral=True,
            )

        try:
            await membro.timeout(discord.utils.utcnow() + timedelta(seconds=segundos), reason=motivo)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra aplicar timeout nesse membro."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, membro.id, interaction.user.id, "timeout", motivo, segundos)
        dur_txt = mu.formatar_duracao(segundos)
        embed = mu.embed_punicao("timeout", membro, interaction.user, motivo, dur_txt, registro["id"])
        await interaction.response.send_message(embed=embed)

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            await mu.notificar_usuario(membro, mu.embed_base("🔇 Você recebeu um timeout",
                                        f"**Servidor:** {interaction.guild.name}\n**Duração:** {dur_txt}\n**Motivo:** {motivo}", mu.COR_ALERTA))
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /untimeout ────────────────────────────────────────────────────────
    @app_commands.command(name="untimeout", description="Remove o timeout de um membro.")
    @app_commands.describe(membro="Membro", motivo="Motivo")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        try:
            await membro.timeout(None, reason=motivo)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra remover o timeout desse membro."), ephemeral=True)
        embed = mu.embed_sucesso(f"Timeout de {membro.mention} removido.\n**Motivo:** {motivo}")
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /kick ─────────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Expulsa um membro do servidor.")
    @app_commands.describe(membro="Membro", motivo="Motivo")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar expulsão",
            f"Tem certeza que quer expulsar {membro.mention}?\n**Motivo:** {motivo}",
            exigir=_exige_confirmacao(interaction.guild_id),
        )
        if not confirmado:
            return

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            await mu.notificar_usuario(membro, mu.embed_base("👢 Você foi expulso",
                                        f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}", mu.COR_ERRO))
        try:
            await membro.kick(reason=f"{motivo} — por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=mu.embed_erro("Sem permissão pra expulsar esse membro."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, membro.id, interaction.user.id, "kick", motivo)
        embed = mu.embed_punicao("kick", membro, interaction.user, motivo, punicao_id=registro["id"])
        await _responder(interaction, embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /ban ──────────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Bane um membro/usuário permanentemente.")
    @app_commands.describe(usuario="Usuário (pode ser ID de quem não está no servidor)", motivo="Motivo",
                            apagar_mensagens="Apagar mensagens dos últimos X dias (0-7)")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, usuario: discord.User, motivo: str = "Não informado", apagar_mensagens: app_commands.Range[int, 0, 7] = 0):
        membro = interaction.guild.get_member(usuario.id)
        if membro:
            pode, erro = mu.pode_moderar(interaction.user, membro)
            if not pode:
                return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar banimento",
            f"Tem certeza que quer banir **{usuario}** permanentemente?\n**Motivo:** {motivo}",
            exigir=_exige_confirmacao(interaction.guild_id),
        )
        if not confirmado:
            return

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            await mu.notificar_usuario(usuario, mu.embed_base("🔨 Você foi banido",
                                        f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}", mu.COR_ERRO))
        try:
            await interaction.guild.ban(usuario, reason=f"{motivo} — por {interaction.user}", delete_message_days=apagar_mensagens)
        except discord.Forbidden:
            return await interaction.followup.send(embed=mu.embed_erro("Sem permissão pra banir esse usuário."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, usuario.id, interaction.user.id, "ban", motivo)
        embed = mu.embed_punicao("ban", usuario, interaction.user, motivo, punicao_id=registro["id"])
        await _responder(interaction, embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /tempban ──────────────────────────────────────────────────────────
    @app_commands.command(name="tempban", description="Bane um usuário temporariamente (desbane sozinho ao expirar).")
    @app_commands.describe(usuario="Usuário", duracao="Ex: 1d, 7d, 12h", motivo="Motivo")
    @app_commands.default_permissions(ban_members=True)
    async def tempban(self, interaction: discord.Interaction, usuario: discord.User, duracao: str, motivo: str = "Não informado"):
        segundos = mu.parsear_duracao(duracao)
        if not segundos:
            return await interaction.response.send_message(embed=mu.embed_erro("Duração inválida. Use algo como `1d`, `12h`, `7d`."), ephemeral=True)

        membro = interaction.guild.get_member(usuario.id)
        if membro:
            pode, erro = mu.pode_moderar(interaction.user, membro)
            if not pode:
                return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar ban temporário",
            f"Banir **{usuario}** por **{mu.formatar_duracao(segundos)}**?\n**Motivo:** {motivo}",
            exigir=_exige_confirmacao(interaction.guild_id),
        )
        if not confirmado:
            return

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            await mu.notificar_usuario(usuario, mu.embed_base("⏳🔨 Você foi banido temporariamente",
                                        f"**Servidor:** {interaction.guild.name}\n**Duração:** {mu.formatar_duracao(segundos)}\n**Motivo:** {motivo}", mu.COR_ERRO))
        try:
            await interaction.guild.ban(usuario, reason=f"[TEMPBAN {duracao}] {motivo} — por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=mu.embed_erro("Sem permissão pra banir esse usuário."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, usuario.id, interaction.user.id, "tempban", motivo, segundos)
        embed = mu.embed_punicao("tempban", usuario, interaction.user, motivo, mu.formatar_duracao(segundos), registro["id"])
        await _responder(interaction, embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /unban ────────────────────────────────────────────────────────────
    @app_commands.command(name="unban", description="Remove o banimento de um usuário pelo ID.")
    @app_commands.describe(user_id="ID do usuário banido", motivo="Motivo")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, motivo: str = "Não informado"):
        try:
            uid = int(user_id)
        except ValueError:
            return await interaction.response.send_message(embed=mu.embed_erro("ID inválido."), ephemeral=True)

        try:
            await interaction.guild.unban(discord.Object(id=uid), reason=f"{motivo} — por {interaction.user}")
        except discord.NotFound:
            return await interaction.response.send_message(embed=mu.embed_erro("Esse usuário não está banido."), ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra desbanir."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, uid, interaction.user.id, "unban", motivo)
        embed = mu.embed_base("♻️ Usuário desbanido", f"**ID:** `{uid}`\n**Motivo:** {motivo}", mu.COR_SUCESSO)
        embed.set_footer(text=f"Caso #{registro['id']}")
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /softban ──────────────────────────────────────────────────────────
    @app_commands.command(name="softban", description="Bane e desbane na hora, apagando as mensagens recentes do membro.")
    @app_commands.describe(membro="Membro", motivo="Motivo", apagar_dias="Dias de mensagens a apagar (1-7)")
    @app_commands.default_permissions(ban_members=True)
    async def softban(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado", apagar_dias: app_commands.Range[int, 1, 7] = 1):
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar softban",
            f"Softban em {membro.mention} (bane, apaga mensagens de {apagar_dias}d e desbane em seguida)?\n**Motivo:** {motivo}",
            exigir=_exige_confirmacao(interaction.guild_id),
        )
        if not confirmado:
            return

        cfg = mu.get_config(interaction.guild_id)
        if cfg.get("dm_ao_punir"):
            await mu.notificar_usuario(membro, mu.embed_base("🧹🔨 Você levou um softban",
                                        f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}\nVocê pode voltar a entrar no servidor.", mu.COR_ALERTA))
        try:
            await interaction.guild.ban(membro, reason=f"[SOFTBAN] {motivo} — por {interaction.user}", delete_message_days=apagar_dias)
            await interaction.guild.unban(membro, reason="Softban — desbanimento automático")
        except discord.Forbidden:
            return await interaction.followup.send(embed=mu.embed_erro("Sem permissão pra executar o softban."), ephemeral=True)

        registro = mu.registrar_punicao(interaction.guild_id, membro.id, interaction.user.id, "softban", motivo)
        embed = mu.embed_punicao("softban", membro, interaction.user, motivo, punicao_id=registro["id"])
        await _responder(interaction, embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /clear ────────────────────────────────────────────────────────────
    @app_commands.command(name="clear", description="Apaga mensagens do canal.")
    @app_commands.describe(quantidade="Número de mensagens (1-1000)", membro="Apagar só mensagens desse membro (opcional)")
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, quantidade: app_commands.Range[int, 1, 1000], membro: discord.Member = None):
        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar limpeza de mensagens",
            f"Apagar até **{quantidade}** mensagens em {interaction.channel.mention}" + (f" de {membro.mention}" if membro else "") + "?",
            exigir=_exige_confirmacao(interaction.guild_id) and quantidade > 20,
        )
        if not confirmado:
            return

        def checar(m):
            return membro is None or m.author.id == membro.id

        try:
            apagadas = await interaction.channel.purge(limit=quantidade, check=checar)
        except discord.Forbidden:
            return await _responder(interaction, mu.embed_erro("Sem permissão pra apagar mensagens nesse canal."))

        embed = mu.embed_sucesso(f"🧽 **{len(apagadas)}** mensagens apagadas em {interaction.channel.mention}.")
        await _responder(interaction, embed, ephemeral=True)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /slowmode ─────────────────────────────────────────────────────────
    @app_commands.command(name="slowmode", description="Define o modo lento do canal atual.")
    @app_commands.describe(segundos="Intervalo em segundos (0 pra desativar, máx 21600)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, segundos: app_commands.Range[int, 0, 21600]):
        try:
            await interaction.channel.edit(slowmode_delay=segundos)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)

        texto = "desativado" if segundos == 0 else f"definido para {mu.formatar_duracao(segundos)}"
        embed = mu.embed_sucesso(f"🐌 Slowmode {texto} em {interaction.channel.mention}.")
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /nick ─────────────────────────────────────────────────────────────
    @app_commands.command(name="nick", description="Altera o apelido de um membro.")
    @app_commands.describe(membro="Membro", novo_nick="Novo apelido (vazio pra resetar)")
    @app_commands.default_permissions(manage_nicknames=True)
    async def nick(self, interaction: discord.Interaction, membro: discord.Member, novo_nick: str = None):
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)
        try:
            await membro.edit(nick=novo_nick, reason=f"Alterado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra alterar o apelido desse membro."), ephemeral=True)

        texto = f"Apelido de {membro.mention} alterado para **{novo_nick}**." if novo_nick else f"Apelido de {membro.mention} resetado."
        embed = mu.embed_sucesso(f"✏️ {texto}")
        await interaction.response.send_message(embed=embed)

    # ── /lock e /unlock ───────────────────────────────────────────────────
    @app_commands.command(name="lock", description="Tranca o canal atual (impede @everyone de enviar mensagens).")
    @app_commands.describe(motivo="Motivo (opcional)")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, motivo: str = "Não informado"):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=motivo)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)
        embed = mu.embed_base("🔒 Canal trancado", f"{interaction.channel.mention} foi trancado.\n**Motivo:** {motivo}", mu.COR_ALERTA)
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    @app_commands.command(name="unlock", description="Destranca o canal atual.")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)
        embed = mu.embed_base("🔓 Canal destrancado", f"{interaction.channel.mention} foi destrancado.", mu.COR_SUCESSO)
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(self.bot, interaction.guild, embed)

    # ── /cargo (grupo) ────────────────────────────────────────────────────
    cargo_group = app_commands.Group(name="cargo", description="Gerenciamento de cargos de membros.",
                                      default_permissions=discord.Permissions(manage_roles=True))

    @cargo_group.command(name="adicionar", description="Adiciona um cargo a um membro.")
    async def cargo_adicionar(self, interaction: discord.Interaction, membro: discord.Member, cargo: discord.Role):
        if cargo >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=mu.embed_erro("Esse cargo está acima do meu cargo mais alto."), ephemeral=True)
        if interaction.user.id != interaction.guild.owner_id and cargo >= interaction.user.top_role:
            return await interaction.response.send_message(embed=mu.embed_erro("Você não pode atribuir um cargo igual ou acima do seu."), ephemeral=True)
        try:
            await membro.add_roles(cargo, reason=f"Adicionado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra adicionar esse cargo."), ephemeral=True)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Cargo {cargo.mention} adicionado a {membro.mention}."))

    @cargo_group.command(name="remover", description="Remove um cargo de um membro.")
    async def cargo_remover(self, interaction: discord.Interaction, membro: discord.Member, cargo: discord.Role):
        if interaction.user.id != interaction.guild.owner_id and cargo >= interaction.user.top_role:
            return await interaction.response.send_message(embed=mu.embed_erro("Você não pode remover um cargo igual ou acima do seu."), ephemeral=True)
        try:
            await membro.remove_roles(cargo, reason=f"Removido por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra remover esse cargo."), ephemeral=True)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Cargo {cargo.mention} removido de {membro.mention}."))

    # ── /canal (grupo) ────────────────────────────────────────────────────
    canal_group = app_commands.Group(name="canal", description="Gerenciamento de canais.",
                                      default_permissions=discord.Permissions(manage_channels=True))

    @canal_group.command(name="criar", description="Cria um novo canal de texto.")
    async def canal_criar(self, interaction: discord.Interaction, nome: str, categoria: discord.CategoryChannel = None):
        try:
            canal = await interaction.guild.create_text_channel(nome, category=categoria, reason=f"Criado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra criar canais."), ephemeral=True)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Canal {canal.mention} criado."))

    @canal_group.command(name="deletar", description="Deleta um canal.")
    async def canal_deletar(self, interaction: discord.Interaction, canal: discord.abc.GuildChannel = None):
        alvo = canal or interaction.channel
        confirmado, interaction = await mu.confirmar_acao(
            interaction, "Confirmar exclusão de canal", f"Tem certeza que quer deletar **#{alvo.name}**? Essa ação é irreversível.",
            exigir=_exige_confirmacao(interaction.guild_id),
        )
        if not confirmado:
            return
        try:
            await alvo.delete(reason=f"Deletado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=mu.embed_erro("Sem permissão pra deletar esse canal."), ephemeral=True)
        await _responder(interaction, mu.embed_sucesso(f"Canal **#{alvo.name}** deletado."))

    @canal_group.command(name="renomear", description="Renomeia o canal atual.")
    async def canal_renomear(self, interaction: discord.Interaction, novo_nome: str):
        try:
            await interaction.channel.edit(name=novo_nome, reason=f"Renomeado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra renomear esse canal."), ephemeral=True)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Canal renomeado para **#{novo_nome}**."))

    # ── /thread (grupo) ───────────────────────────────────────────────────
    thread_group = app_commands.Group(name="thread", description="Gerenciamento de threads.",
                                       default_permissions=discord.Permissions(manage_threads=True))

    @thread_group.command(name="trancar", description="Tranca a thread atual.")
    async def thread_trancar(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message(embed=mu.embed_erro("Use esse comando dentro de uma thread."), ephemeral=True)
        await interaction.channel.edit(locked=True, reason=f"Trancada por {interaction.user}")
        await interaction.response.send_message(embed=mu.embed_sucesso("🔒 Thread trancada."))

    @thread_group.command(name="destrancar", description="Destranca a thread atual.")
    async def thread_destrancar(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message(embed=mu.embed_erro("Use esse comando dentro de uma thread."), ephemeral=True)
        await interaction.channel.edit(locked=False, reason=f"Destrancada por {interaction.user}")
        await interaction.response.send_message(embed=mu.embed_sucesso("🔓 Thread destrancada."))

    @thread_group.command(name="arquivar", description="Arquiva a thread atual.")
    async def thread_arquivar(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message(embed=mu.embed_erro("Use esse comando dentro de uma thread."), ephemeral=True)
        await interaction.channel.edit(archived=True, reason=f"Arquivada por {interaction.user}")
        await interaction.response.send_message(embed=mu.embed_sucesso("🗃️ Thread arquivada."))


async def _responder(interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = False):
    """Depois de uma ConfirmarView, a resposta original já foi usada — usa followup."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException:
        pass


async def setup(bot: commands.Bot):
    # Os grupos (cargo/canal/thread) são atributos de classe do Cog e o
    # discord.py já os registra automaticamente na árvore de slash commands
    # dentro de add_cog — não é necessário (nem permitido) adicioná-los de novo.
    await bot.add_cog(Moderation(bot))
