from __future__ import annotations

import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict, deque

from cogs import mod_utils as mu

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Anti-Nuke
#  Arquivo: cogs/antinuke.py
#
#  Diferente do Anti-Raid (que olha pra ENTRADA de membros), esse aqui olha
#  pra AÇÕES destrutivas de quem já está dentro do servidor — inclusive
#  staff/admin com cargo legítimo, caso a conta seja comprometida ou alguém
#  enlouqueça e resolva deletar tudo.
#
#  Monitora, via audit log, quem está:
#   • deletando ou criando canais em massa
#   • deletando ou criando cargos em massa
#   • banindo membros em massa
#   • expulsando membros em massa
#
#  Se algum usuário passar do limite configurado numa janela de tempo curta,
#  o bot AUTOMATICAMENTE remove todos os cargos dele (tirando o poder de
#  continuar destruindo o servidor), podendo também colocar em quarentena
#  ou banir, dependendo da configuração.
# ─────────────────────────────────────────────────────────────────────────────


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> {evento: deque[timestamps]}
        self.eventos: dict[int, dict[int, dict[str, deque]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))
        )
        # trava simples pra não punir o mesmo usuário duas vezes em paralelo
        self._punindo: set[tuple[int, int]] = set()

    # ── Helpers ───────────────────────────────────────────────────────────
    def _imune(self, guild: discord.Guild, user_id: int, cfg: dict) -> bool:
        if user_id == guild.owner_id:
            return True
        if user_id == self.bot.user.id:
            return True
        if user_id in set(cfg.get("whitelist_ids", [])):
            return True
        return False

    async def _pegar_executor(self, guild: discord.Guild, action: discord.AuditLogAction,
                               alvo_id: int | None = None) -> discord.Member | discord.User | None:
        """Busca no audit log quem foi o autor de uma ação recente."""
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if alvo_id is None or (entry.target and getattr(entry.target, "id", None) == alvo_id):
                    # só considera entradas bem recentes (últimos 10s) pra evitar falso positivo
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() <= 10:
                        return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    def _registrar(self, guild_id: int, user_id: int, evento: str, cfg: dict) -> int:
        agora = time.time()
        dq = self.eventos[guild_id][user_id][evento]
        dq.append(agora)
        janela = cfg.get("janela_segundos", 20)
        recentes = [t for t in dq if agora - t <= janela]
        return len(recentes)

    async def _punir(self, guild: discord.Guild, user_id: int, cfg: dict, motivo: str):
        chave = (guild.id, user_id)
        if chave in self._punindo:
            return
        self._punindo.add(chave)
        try:
            membro = guild.get_member(user_id)
            if membro is None:
                try:
                    membro = await guild.fetch_member(user_id)
                except (discord.NotFound, discord.HTTPException):
                    membro = None

            acao = cfg.get("acao", "remover_cargos")
            resultado = "sem ação (usuário não está mais no servidor)"

            if membro is not None:
                try:
                    if acao == "ban":
                        await guild.ban(membro, reason=motivo, delete_message_days=0)
                        mu.registrar_punicao(guild.id, membro.id, self.bot.user.id, "ban", motivo)
                        resultado = "banido"
                    elif acao == "quarentena" and cfg.get("cargo_quarentena"):
                        cargos_removidos = [r for r in membro.roles if r.name != "@everyone"]
                        if cargos_removidos:
                            await membro.remove_roles(*cargos_removidos, reason=motivo)
                        cargo = guild.get_role(cfg["cargo_quarentena"])
                        if cargo:
                            await membro.add_roles(cargo, reason=motivo)
                        resultado = "cargos removidos e colocado em quarentena"
                    else:
                        cargos_removidos = [r for r in membro.roles if r.name != "@everyone"]
                        if cargos_removidos:
                            await membro.remove_roles(*cargos_removidos, reason=motivo)
                        resultado = f"{len(cargos_removidos)} cargo(s) removido(s)"
                except discord.Forbidden:
                    resultado = "⚠️ falhou — meu cargo está abaixo do cargo do usuário, não consegui remover"
                except discord.HTTPException as e:
                    resultado = f"⚠️ falhou — erro do Discord: {e}"

            embed = mu.embed_base(
                "🚨 ANTI-NUKE ACIONADO",
                f"**Usuário:** <@{user_id}> (`{user_id}`)\n"
                f"**Motivo:** {motivo}\n"
                f"**Ação tomada:** {resultado}",
                mu.COR_ERRO,
            )
            await mu.enviar_log_antinuke(self.bot, guild, embed)
        finally:
            self._punindo.discard(chave)

    async def _checar(self, guild: discord.Guild, action: discord.AuditLogAction, evento: str,
                       limite_chave: str, descricao: str, alvo_id: int | None = None):
        cfg = mu.get_antinuke(guild.id)
        if not cfg.get("ativo", True):
            return

        executor = await self._pegar_executor(guild, action, alvo_id)
        if executor is None:
            return

        if self._imune(guild, executor.id, cfg):
            return

        if executor.bot and not cfg.get("punir_bots_nao_whitelistados", True):
            return

        limite = cfg.get(limite_chave)
        if limite is None:
            return

        qtd = self._registrar(guild.id, executor.id, evento, cfg)
        if qtd >= limite:
            janela = cfg.get("janela_segundos", 20)
            motivo = f"{descricao}: {qtd} ações em {janela}s (limite: {limite})"
            await self._punir(guild, executor.id, cfg, motivo)
            # zera o contador desse evento pra não ficar punindo repetido a cada novo hit
            self.eventos[guild.id][executor.id][evento].clear()

    # ── Listeners ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._checar(channel.guild, discord.AuditLogAction.channel_delete,
                            "canal_delete", "limite_canais", "Deletando canais em massa")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._checar(channel.guild, discord.AuditLogAction.channel_create,
                            "canal_create", "limite_canais", "Criando canais em massa (spam)")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._checar(role.guild, discord.AuditLogAction.role_delete,
                            "cargo_delete", "limite_cargos", "Deletando cargos em massa")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._checar(role.guild, discord.AuditLogAction.role_create,
                            "cargo_create", "limite_cargos", "Criando cargos em massa (spam)")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self._checar(guild, discord.AuditLogAction.ban,
                            "ban", "limite_banimentos", "Banindo membros em massa", alvo_id=user.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # on_member_remove dispara em qualquer saída (kick ou o próprio membro saindo).
        # Só contamos se o audit log confirmar que foi um kick de fato.
        await self._checar(member.guild, discord.AuditLogAction.kick,
                            "kick", "limite_expulsoes", "Expulsando membros em massa", alvo_id=member.id)

    # ── /antinuke (grupo de configuração) ────────────────────────────────
    antinuke_group = app_commands.Group(name="antinuke", description="Configurações do sistema Anti-Nuke.",
                                         default_permissions=discord.Permissions(administrator=True))

    @antinuke_group.command(name="status", description="Mostra a configuração atual do Anti-Nuke.")
    async def antinuke_status(self, interaction: discord.Interaction):
        cfg = mu.get_antinuke(interaction.guild_id)
        whitelist = ", ".join(f"<@{i}>" for i in cfg.get("whitelist_ids", [])) or "nenhum"
        linhas = [
            f"**Ativo:** {'✅' if cfg['ativo'] else '❌'}",
            f"**Janela de detecção:** {cfg['janela_segundos']}s",
            f"**Limite de canais (criar/deletar):** {cfg['limite_canais']}",
            f"**Limite de cargos (criar/deletar):** {cfg['limite_cargos']}",
            f"**Limite de banimentos:** {cfg['limite_banimentos']}",
            f"**Limite de expulsões:** {cfg['limite_expulsoes']}",
            f"**Ação aplicada:** `{cfg['acao']}`",
            f"**Whitelist:** {whitelist}",
        ]
        embed = mu.embed_base("🛡️ Configuração do Anti-Nuke", "\n".join(linhas), mu.COR_INFO)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antinuke_group.command(name="ativo", description="Liga/desliga o Anti-Nuke.")
    async def antinuke_ativo(self, interaction: discord.Interaction, ativo: bool):
        mu.atualizar_antinuke(interaction.guild_id, ativo=ativo)
        embed = mu.embed_sucesso(f"Anti-Nuke {'ativado ✅' if ativo else 'desativado ❌'}.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antinuke_group.command(name="configurar", description="Ajusta os limites de detecção do Anti-Nuke.")
    @app_commands.describe(
        janela_segundos="Janela de tempo pra contar as ações",
        limite_canais="Nº de canais criados/deletados na janela pra acionar",
        limite_cargos="Nº de cargos criados/deletados na janela pra acionar",
        limite_banimentos="Nº de banimentos na janela pra acionar",
        limite_expulsoes="Nº de expulsões na janela pra acionar",
    )
    async def antinuke_configurar(self, interaction: discord.Interaction,
                                   janela_segundos: app_commands.Range[int, 5, 300] = None,
                                   limite_canais: app_commands.Range[int, 1, 50] = None,
                                   limite_cargos: app_commands.Range[int, 1, 50] = None,
                                   limite_banimentos: app_commands.Range[int, 1, 50] = None,
                                   limite_expulsoes: app_commands.Range[int, 1, 50] = None):
        kwargs = {}
        if janela_segundos is not None:
            kwargs["janela_segundos"] = janela_segundos
        if limite_canais is not None:
            kwargs["limite_canais"] = limite_canais
        if limite_cargos is not None:
            kwargs["limite_cargos"] = limite_cargos
        if limite_banimentos is not None:
            kwargs["limite_banimentos"] = limite_banimentos
        if limite_expulsoes is not None:
            kwargs["limite_expulsoes"] = limite_expulsoes
        if not kwargs:
            return await interaction.response.send_message(embed=mu.embed_erro("Informe ao menos um parâmetro."), ephemeral=True)
        mu.atualizar_antinuke(interaction.guild_id, **kwargs)
        await interaction.response.send_message(embed=mu.embed_sucesso("Configuração do Anti-Nuke atualizada."), ephemeral=True)

    @antinuke_group.command(name="acao", description="Define o que acontece com quem for detectado nukeando o servidor.")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Remover todos os cargos (recomendado)", value="remover_cargos"),
        app_commands.Choice(name="Remover cargos e colocar em quarentena", value="quarentena"),
        app_commands.Choice(name="Banir imediatamente", value="ban"),
    ])
    async def antinuke_acao(self, interaction: discord.Interaction, acao: app_commands.Choice[str]):
        mu.atualizar_antinuke(interaction.guild_id, acao=acao.value)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Ação do Anti-Nuke definida como **{acao.name}**."), ephemeral=True)

    @antinuke_group.command(name="cargo-quarentena", description="Define o cargo usado quando a ação é 'quarentena'.")
    async def antinuke_cargo_quarentena(self, interaction: discord.Interaction, cargo: discord.Role):
        mu.atualizar_antinuke(interaction.guild_id, cargo_quarentena=cargo.id)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Cargo de quarentena definido como {cargo.mention}."), ephemeral=True)

    @antinuke_group.command(name="whitelist-add", description="Adiciona alguém à whitelist do Anti-Nuke (nunca será punido).")
    async def antinuke_whitelist_add(self, interaction: discord.Interaction, usuario: discord.Member):
        cfg = mu.get_antinuke(interaction.guild_id)
        whitelist = set(cfg.get("whitelist_ids", []))
        whitelist.add(usuario.id)
        mu.atualizar_antinuke(interaction.guild_id, whitelist_ids=list(whitelist))
        await interaction.response.send_message(embed=mu.embed_sucesso(f"{usuario.mention} adicionado à whitelist do Anti-Nuke."), ephemeral=True)

    @antinuke_group.command(name="whitelist-remove", description="Remove alguém da whitelist do Anti-Nuke.")
    async def antinuke_whitelist_remove(self, interaction: discord.Interaction, usuario: discord.Member):
        cfg = mu.get_antinuke(interaction.guild_id)
        whitelist = set(cfg.get("whitelist_ids", []))
        whitelist.discard(usuario.id)
        mu.atualizar_antinuke(interaction.guild_id, whitelist_ids=list(whitelist))
        await interaction.response.send_message(embed=mu.embed_sucesso(f"{usuario.mention} removido da whitelist do Anti-Nuke."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
