from __future__ import annotations

import re
import discord
from discord.ext import commands
from datetime import timedelta

from cogs import mod_utils as mu

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Painel Rápido de Moderação
#  Arquivo: cogs/mod_setup.py
#
#  Comando de prefixo `!setup-moderacao`: manda um embed com um painel de
#  botões cobrindo as principais ações de moderação. Cada botão abre um
#  Modal pedindo os dados necessários (usuário, motivo, duração etc.) —
#  já que um botão do Discord sozinho não recebe input de texto.
#
#  O painel é uma View persistente (custom_id fixo), então continua
#  funcionando normalmente mesmo depois de reiniciar o bot.
# ─────────────────────────────────────────────────────────────────────────────

REGEX_ID = re.compile(r"\d{15,25}")


def _extrair_id(texto: str) -> int | None:
    m = REGEX_ID.search(texto or "")
    return int(m.group()) if m else None


async def _resolver_membro(interaction: discord.Interaction, texto: str) -> discord.Member | None:
    uid = _extrair_id(texto)
    if not uid:
        return None
    membro = interaction.guild.get_member(uid)
    if membro is None:
        try:
            membro = await interaction.guild.fetch_member(uid)
        except (discord.NotFound, discord.HTTPException):
            return None
    return membro


# ── Modal genérico usado por warn / kick / ban / tempban / timeout / softban / unban ──
class AcaoModal(discord.ui.Modal):
    TITULOS = {
        "warn": "⚠️ Aplicar Advertência", "timeout": "🔇 Aplicar Timeout",
        "kick": "👢 Expulsar Membro", "ban": "🔨 Banir Usuário",
        "tempban": "⏳🔨 Ban Temporário", "unban": "♻️ Remover Banimento",
        "softban": "🧹🔨 Softban",
    }

    def __init__(self, acao: str):
        super().__init__(title=self.TITULOS.get(acao, acao.capitalize()))
        self.acao = acao

        label_usuario = "ID do usuário banido" if acao == "unban" else "ID ou menção do usuário"
        self.usuario_input = discord.ui.TextInput(label=label_usuario, placeholder="Ex: 123456789012345678", required=True, max_length=50)
        self.add_item(self.usuario_input)

        self.duracao_input = None
        if acao in ("timeout", "tempban"):
            self.duracao_input = discord.ui.TextInput(label="Duração (ex: 10m, 1h, 7d)", placeholder="10m", required=True, max_length=20)
            self.add_item(self.duracao_input)

        self.motivo_input = discord.ui.TextInput(label="Motivo", style=discord.TextStyle.paragraph, required=False, max_length=300, placeholder="Não informado")
        self.add_item(self.motivo_input)

    async def on_submit(self, interaction: discord.Interaction):
        motivo = str(self.motivo_input.value) or "Não informado"
        acao = self.acao
        guild = interaction.guild
        cfg = mu.get_config(guild.id)

        if acao == "unban":
            uid = _extrair_id(str(self.usuario_input.value))
            if not uid:
                return await interaction.response.send_message(embed=mu.embed_erro("ID inválido."), ephemeral=True)
            try:
                await guild.unban(discord.Object(id=uid), reason=f"{motivo} — por {interaction.user}")
            except discord.NotFound:
                return await interaction.response.send_message(embed=mu.embed_erro("Esse usuário não está banido."), ephemeral=True)
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra desbanir."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, uid, interaction.user.id, "unban", motivo)
            embed = mu.embed_base("♻️ Usuário desbanido", f"**ID:** `{uid}`\n**Motivo:** {motivo}", mu.COR_SUCESSO)
            embed.set_footer(text=f"Caso #{registro['id']}")
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)
            return

        if acao == "ban":
            uid = _extrair_id(str(self.usuario_input.value))
            if not uid:
                return await interaction.response.send_message(embed=mu.embed_erro("ID inválido."), ephemeral=True)
            membro = guild.get_member(uid)
            if membro:
                pode, erro = mu.pode_moderar(interaction.user, membro)
                if not pode:
                    return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)
            usuario_obj = membro or discord.Object(id=uid)
            try:
                if cfg.get("dm_ao_punir") and membro:
                    await mu.notificar_usuario(membro, mu.embed_base("🔨 Você foi banido", f"**Servidor:** {guild.name}\n**Motivo:** {motivo}", mu.COR_ERRO))
                await guild.ban(usuario_obj, reason=f"{motivo} — por {interaction.user}")
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra banir esse usuário."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, uid, interaction.user.id, "ban", motivo)
            embed = mu.embed_base("🔨 Ban aplicado", f"**Usuário:** `{uid}`\n**Responsável:** {interaction.user.mention}\n**Motivo:** {motivo}", mu.COR_MODERACAO)
            embed.set_footer(text=f"Caso #{registro['id']}")
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)
            return

        # Ações que exigem o membro estar no servidor: warn, timeout, kick, tempban, softban
        membro = await _resolver_membro(interaction, str(self.usuario_input.value))
        if membro is None:
            return await interaction.response.send_message(embed=mu.embed_erro("Não encontrei esse membro no servidor. Confira o ID/menção."), ephemeral=True)

        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)

        if acao == "warn":
            registro = mu.registrar_punicao(guild.id, membro.id, interaction.user.id, "warn", motivo)
            total = len(mu.avisos_usuario(guild.id, membro.id))
            if cfg.get("dm_ao_punir"):
                await mu.notificar_usuario(membro, mu.embed_base("⚠️ Você recebeu uma advertência", f"**Servidor:** {guild.name}\n**Motivo:** {motivo}\n**Total de avisos:** {total}", mu.COR_ALERTA))
            embed = mu.embed_punicao("warn", membro, interaction.user, motivo, punicao_id=registro["id"])
            embed.add_field(name="Total de avisos ativos", value=str(total), inline=False)
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)

        elif acao == "timeout":
            segundos = mu.parsear_duracao(str(self.duracao_input.value))
            if not segundos or segundos > 28 * 86400:
                return await interaction.response.send_message(embed=mu.embed_erro("Duração inválida (use ex: `10m`, `1h`, `7d`, máx 28d)."), ephemeral=True)
            try:
                await membro.timeout(discord.utils.utcnow() + timedelta(seconds=segundos), reason=motivo)
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra aplicar timeout nesse membro."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, membro.id, interaction.user.id, "timeout", motivo, segundos)
            dur_txt = mu.formatar_duracao(segundos)
            if cfg.get("dm_ao_punir"):
                await mu.notificar_usuario(membro, mu.embed_base("🔇 Você recebeu um timeout", f"**Servidor:** {guild.name}\n**Duração:** {dur_txt}\n**Motivo:** {motivo}", mu.COR_ALERTA))
            embed = mu.embed_punicao("timeout", membro, interaction.user, motivo, dur_txt, registro["id"])
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)

        elif acao == "kick":
            if cfg.get("dm_ao_punir"):
                await mu.notificar_usuario(membro, mu.embed_base("👢 Você foi expulso", f"**Servidor:** {guild.name}\n**Motivo:** {motivo}", mu.COR_ERRO))
            try:
                await membro.kick(reason=f"{motivo} — por {interaction.user}")
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra expulsar esse membro."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, membro.id, interaction.user.id, "kick", motivo)
            embed = mu.embed_punicao("kick", membro, interaction.user, motivo, punicao_id=registro["id"])
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)

        elif acao == "tempban":
            segundos = mu.parsear_duracao(str(self.duracao_input.value))
            if not segundos:
                return await interaction.response.send_message(embed=mu.embed_erro("Duração inválida (use ex: `1d`, `12h`, `7d`)."), ephemeral=True)
            if cfg.get("dm_ao_punir"):
                await mu.notificar_usuario(membro, mu.embed_base("⏳🔨 Você foi banido temporariamente", f"**Servidor:** {guild.name}\n**Duração:** {mu.formatar_duracao(segundos)}\n**Motivo:** {motivo}", mu.COR_ERRO))
            try:
                await guild.ban(membro, reason=f"[TEMPBAN] {motivo} — por {interaction.user}")
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra banir esse membro."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, membro.id, interaction.user.id, "tempban", motivo, segundos)
            embed = mu.embed_punicao("tempban", membro, interaction.user, motivo, mu.formatar_duracao(segundos), registro["id"])
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)

        elif acao == "softban":
            if cfg.get("dm_ao_punir"):
                await mu.notificar_usuario(membro, mu.embed_base("🧹🔨 Você levou um softban", f"**Servidor:** {guild.name}\n**Motivo:** {motivo}", mu.COR_ALERTA))
            try:
                await guild.ban(membro, reason=f"[SOFTBAN] {motivo} — por {interaction.user}", delete_message_days=1)
                await guild.unban(membro, reason="Softban — desbanimento automático")
            except discord.Forbidden:
                return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra executar o softban."), ephemeral=True)
            registro = mu.registrar_punicao(guild.id, membro.id, interaction.user.id, "softban", motivo)
            embed = mu.embed_punicao("softban", membro, interaction.user, motivo, punicao_id=registro["id"])
            await interaction.response.send_message(embed=embed)
            await mu.enviar_log_moderacao(interaction.client, guild, embed)


class ClearModal(discord.ui.Modal, title="🧽 Limpar Mensagens"):
    quantidade_input = discord.ui.TextInput(label="Quantidade (1-1000)", placeholder="50", required=True, max_length=4)
    usuario_input = discord.ui.TextInput(label="ID do usuário (opcional)", required=False, max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantidade = max(1, min(1000, int(str(self.quantidade_input.value))))
        except ValueError:
            return await interaction.response.send_message(embed=mu.embed_erro("Quantidade inválida."), ephemeral=True)

        uid = _extrair_id(str(self.usuario_input.value)) if self.usuario_input.value else None

        def checar(m):
            return uid is None or m.author.id == uid

        await interaction.response.defer(ephemeral=True, thinking=True)
        apagadas = await interaction.channel.purge(limit=quantidade, check=checar)
        embed = mu.embed_sucesso(f"🧽 **{len(apagadas)}** mensagens apagadas em {interaction.channel.mention}.")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await mu.enviar_log_moderacao(interaction.client, interaction.guild, embed)


class SlowmodeModal(discord.ui.Modal, title="🐌 Definir Slowmode"):
    segundos_input = discord.ui.TextInput(label="Segundos (0 pra desativar, máx 21600)", placeholder="10", required=True, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            segundos = max(0, min(21600, int(str(self.segundos_input.value))))
        except ValueError:
            return await interaction.response.send_message(embed=mu.embed_erro("Valor inválido."), ephemeral=True)
        try:
            await interaction.channel.edit(slowmode_delay=segundos)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)
        texto = "desativado" if segundos == 0 else f"definido para {mu.formatar_duracao(segundos)}"
        embed = mu.embed_sucesso(f"🐌 Slowmode {texto} em {interaction.channel.mention}.")
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(interaction.client, interaction.guild, embed)


class NickModal(discord.ui.Modal, title="✏️ Alterar Apelido"):
    usuario_input = discord.ui.TextInput(label="ID ou menção do usuário", required=True, max_length=50)
    nick_input = discord.ui.TextInput(label="Novo apelido (vazio pra resetar)", required=False, max_length=32)

    async def on_submit(self, interaction: discord.Interaction):
        membro = await _resolver_membro(interaction, str(self.usuario_input.value))
        if membro is None:
            return await interaction.response.send_message(embed=mu.embed_erro("Não encontrei esse membro no servidor."), ephemeral=True)
        pode, erro = mu.pode_moderar(interaction.user, membro)
        if not pode:
            return await interaction.response.send_message(embed=mu.embed_erro(erro), ephemeral=True)
        novo_nick = str(self.nick_input.value) or None
        try:
            await membro.edit(nick=novo_nick, reason=f"Alterado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra alterar o apelido desse membro."), ephemeral=True)
        texto = f"Apelido de {membro.mention} alterado para **{novo_nick}**." if novo_nick else f"Apelido de {membro.mention} resetado."
        await interaction.response.send_message(embed=mu.embed_sucesso(f"✏️ {texto}"))


# ── Painel principal (View persistente com custom_id fixo) ──────────────────
class PainelModeracaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _checar_permissao(self, interaction: discord.Interaction) -> bool:
        if not mu.eh_staff(interaction.user, interaction.guild_id):
            await interaction.response.send_message(embed=mu.embed_erro("Você não tem permissão pra usar o painel de moderação."), ephemeral=True)
            return False
        return True

    # linha 0
    @discord.ui.button(label="Advertir", emoji="⚠️", style=discord.ButtonStyle.primary, custom_id="painel_mod:warn", row=0)
    async def btn_warn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("warn"))

    @discord.ui.button(label="Timeout", emoji="🔇", style=discord.ButtonStyle.primary, custom_id="painel_mod:timeout", row=0)
    async def btn_timeout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("timeout"))

    @discord.ui.button(label="Expulsar", emoji="👢", style=discord.ButtonStyle.danger, custom_id="painel_mod:kick", row=0)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("kick"))

    @discord.ui.button(label="Banir", emoji="🔨", style=discord.ButtonStyle.danger, custom_id="painel_mod:ban", row=0)
    async def btn_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("ban"))

    # linha 1
    @discord.ui.button(label="Ban Temporário", emoji="⏳", style=discord.ButtonStyle.danger, custom_id="painel_mod:tempban", row=1)
    async def btn_tempban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("tempban"))

    @discord.ui.button(label="Desbanir", emoji="♻️", style=discord.ButtonStyle.success, custom_id="painel_mod:unban", row=1)
    async def btn_unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("unban"))

    @discord.ui.button(label="Softban", emoji="🧹", style=discord.ButtonStyle.danger, custom_id="painel_mod:softban", row=1)
    async def btn_softban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(AcaoModal("softban"))

    @discord.ui.button(label="Limpar Mensagens", emoji="🧽", style=discord.ButtonStyle.secondary, custom_id="painel_mod:clear", row=1)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(ClearModal())

    # linha 2
    @discord.ui.button(label="Slowmode", emoji="🐌", style=discord.ButtonStyle.secondary, custom_id="painel_mod:slowmode", row=2)
    async def btn_slowmode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(SlowmodeModal())

    @discord.ui.button(label="Alterar Nick", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="painel_mod:nick", row=2)
    async def btn_nick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._checar_permissao(interaction):
            await interaction.response.send_modal(NickModal())

    @discord.ui.button(label="Trancar Canal", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="painel_mod:lock", row=2)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._checar_permissao(interaction):
            return
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Painel de moderação — {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)
        embed = mu.embed_base("🔒 Canal trancado", f"{interaction.channel.mention} foi trancado por {interaction.user.mention}.", mu.COR_ALERTA)
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(interaction.client, interaction.guild, embed)

    @discord.ui.button(label="Destrancar Canal", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="painel_mod:unlock", row=2)
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._checar_permissao(interaction):
            return
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await interaction.response.send_message(embed=mu.embed_erro("Sem permissão pra editar esse canal."), ephemeral=True)
        embed = mu.embed_base("🔓 Canal destrancado", f"{interaction.channel.mention} foi destrancado por {interaction.user.mention}.", mu.COR_SUCESSO)
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_moderacao(interaction.client, interaction.guild, embed)


def _embed_painel(guild: discord.Guild) -> discord.Embed:
    e = discord.Embed(
        title="🛡️ Painel de Moderação",
        description=(
            "Clique em um dos botões abaixo para executar uma ação de moderação.\n"
            "Cada botão vai abrir uma janela pedindo os dados necessários "
            "(usuário, motivo, duração etc).\n\n"
            "🔒/🔓 **Trancar/Destrancar** agem sobre o canal onde o botão for clicado."
        ),
        color=mu.COR_NEUTRO,
    )
    e.set_footer(text=f"{guild.name} • Sistema de Moderação")
    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    return e


class ModSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="setup-moderacao")
    @commands.has_permissions(administrator=True)
    async def setup_moderacao(self, ctx: commands.Context):
        """Envia o painel de moderação com botões neste canal."""
        view = PainelModeracaoView()
        await ctx.send(embed=_embed_painel(ctx.guild), view=view)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @setup_moderacao.error
    async def setup_moderacao_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=mu.embed_erro("Você precisa ser **Administrador** para usar esse comando."), delete_after=6)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModSetup(bot))
