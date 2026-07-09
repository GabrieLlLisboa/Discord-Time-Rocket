from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from cogs import mod_utils as mu

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Anti-Raid
#  Arquivo: cogs/antiraid.py
#
#  Monitora a taxa de entrada de novos membros. Se muitas entradas
#  acontecerem numa janela curta de tempo, considera um possível raid e
#  aplica a ação configurada (kick / ban / quarentena) nos membros
#  suspeitos, além de poder ativar o "modo de emergência" automaticamente.
# ─────────────────────────────────────────────────────────────────────────────


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.entradas: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))  # guild_id -> deque[timestamps]

    def _conta_suspeita(self, membro: discord.Member, cfg: dict) -> bool:
        idade_dias = (datetime.now(timezone.utc) - membro.created_at).days
        if idade_dias < cfg.get("conta_nova_dias", 7):
            return True
        if cfg.get("bloquear_conta_sem_avatar") and membro.avatar is None:
            return True
        return False

    async def _aplicar_acao_membro(self, membro: discord.Member, cfg: dict, motivo: str):
        acao = cfg.get("acao", "kick")
        try:
            if acao == "ban":
                await membro.ban(reason=motivo, delete_message_days=1)
                mu.registrar_punicao(membro.guild.id, membro.id, self.bot.user.id, "ban", motivo)
            elif acao == "quarentena" and cfg.get("cargo_quarentena"):
                cargo = membro.guild.get_role(cfg["cargo_quarentena"])
                if cargo:
                    await membro.add_roles(cargo, reason=motivo)
            else:
                await membro.kick(reason=motivo)
                mu.registrar_punicao(membro.guild.id, membro.id, self.bot.user.id, "kick", motivo)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        guild = membro.guild
        cfg = mu.get_antiraid(guild.id)
        if not cfg.get("ativo", True):
            return

        agora = time.time()
        entradas = self.entradas[guild.id]
        entradas.append(agora)

        janela = cfg.get("janela_segundos", 10)
        recentes = [t for t in entradas if agora - t <= janela]

        # ── Modo de emergência manual: kicka todo mundo que entrar ──────────
        if cfg.get("modo_emergencia"):
            await self._aplicar_acao_membro(membro, cfg, "Modo de emergência ativo (anti-raid)")
            embed = mu.embed_base("🚨 Modo de emergência: entrada bloqueada",
                                   f"{membro.mention} (`{membro.id}`) foi removido — o modo de emergência está ativo.",
                                   mu.COR_ERRO)
            await mu.enviar_log_antiraid(self.bot, guild, embed)
            return

        # ── Detecção de raid por volume de entradas ─────────────────────────
        if len(recentes) >= cfg.get("limite_entradas", 8):
            suspeita = self._conta_suspeita(membro, cfg)
            if suspeita:
                await self._aplicar_acao_membro(membro, cfg, "Possível raid detectado — conta suspeita durante pico de entradas")

            embed = mu.embed_base(
                "🚨 Possível raid detectado!",
                f"**{len(recentes)}** entradas nos últimos **{janela}s**.\n"
                f"Último membro: {membro.mention} (`{membro.id}`, conta criada <t:{int(membro.created_at.timestamp())}:R>)\n"
                f"Ação aplicada ao membro: **{'sim' if suspeita else 'não (conta não é suspeita)'}**\n\n"
                f"Use `/antiraid emergencia ativo:true` pra travar novas entradas manualmente.",
                mu.COR_ERRO,
            )
            await mu.enviar_log_antiraid(self.bot, guild, embed)

    # ── /antiraid (grupo de configuração) ────────────────────────────────
    antiraid_group = app_commands.Group(name="antiraid", description="Configurações do sistema Anti-Raid.",
                                         default_permissions=discord.Permissions(administrator=True))

    @antiraid_group.command(name="status", description="Mostra a configuração atual do Anti-Raid.")
    async def antiraid_status(self, interaction: discord.Interaction):
        cfg = mu.get_antiraid(interaction.guild_id)
        linhas = [
            f"**Ativo:** {'✅' if cfg['ativo'] else '❌'}",
            f"**Modo de emergência:** {'🚨 ATIVO' if cfg['modo_emergencia'] else '❌ inativo'}",
            f"**Janela de detecção:** {cfg['janela_segundos']}s",
            f"**Limite de entradas p/ considerar raid:** {cfg['limite_entradas']}",
            f"**Conta considerada nova:** menos de {cfg['conta_nova_dias']} dias",
            f"**Ação aplicada:** `{cfg['acao']}`",
            f"**Bloquear contas sem avatar:** {'✅' if cfg['bloquear_conta_sem_avatar'] else '❌'}",
        ]
        embed = mu.embed_base("🛡️ Configuração do Anti-Raid", "\n".join(linhas), mu.COR_INFO)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @antiraid_group.command(name="emergencia", description="Ativa/desativa o modo de emergência (bloqueia todas as entradas).")
    async def antiraid_emergencia(self, interaction: discord.Interaction, ativo: bool):
        mu.atualizar_antiraid(interaction.guild_id, modo_emergencia=ativo)
        if ativo:
            embed = mu.embed_base("🚨 Modo de emergência ATIVADO",
                                   "Todo novo membro que entrar será removido automaticamente até você desativar.",
                                   mu.COR_ERRO)
        else:
            embed = mu.embed_sucesso("Modo de emergência desativado. Entradas voltaram ao normal.")
        await interaction.response.send_message(embed=embed)
        await mu.enviar_log_antiraid(self.bot, interaction.guild, embed)

    @antiraid_group.command(name="configurar", description="Ajusta os limites de detecção do Anti-Raid.")
    @app_commands.describe(
        janela_segundos="Janela de tempo pra contar entradas",
        limite_entradas="Nº de entradas na janela pra considerar raid",
        conta_nova_dias="Idade mínima (dias) pra conta não ser suspeita",
    )
    async def antiraid_configurar(self, interaction: discord.Interaction,
                                   janela_segundos: app_commands.Range[int, 3, 300] = None,
                                   limite_entradas: app_commands.Range[int, 2, 100] = None,
                                   conta_nova_dias: app_commands.Range[int, 0, 90] = None):
        kwargs = {}
        if janela_segundos is not None:
            kwargs["janela_segundos"] = janela_segundos
        if limite_entradas is not None:
            kwargs["limite_entradas"] = limite_entradas
        if conta_nova_dias is not None:
            kwargs["conta_nova_dias"] = conta_nova_dias
        if not kwargs:
            return await interaction.response.send_message(embed=mu.embed_erro("Informe ao menos um parâmetro."), ephemeral=True)
        mu.atualizar_antiraid(interaction.guild_id, **kwargs)
        await interaction.response.send_message(embed=mu.embed_sucesso("Configuração do Anti-Raid atualizada."), ephemeral=True)

    @antiraid_group.command(name="acao", description="Define a ação aplicada a membros suspeitos durante um raid.")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Expulsar (kick)", value="kick"),
        app_commands.Choice(name="Banir (ban)", value="ban"),
        app_commands.Choice(name="Quarentena (cargo)", value="quarentena"),
    ])
    async def antiraid_acao(self, interaction: discord.Interaction, acao: app_commands.Choice[str]):
        mu.atualizar_antiraid(interaction.guild_id, acao=acao.value)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Ação do Anti-Raid definida como **{acao.name}**."), ephemeral=True)

    @antiraid_group.command(name="cargo-quarentena", description="Define o cargo usado na ação de quarentena.")
    async def antiraid_cargo_quarentena(self, interaction: discord.Interaction, cargo: discord.Role):
        mu.atualizar_antiraid(interaction.guild_id, cargo_quarentena=cargo.id)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Cargo de quarentena definido como {cargo.mention}."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
