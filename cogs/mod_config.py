from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs import mod_utils as mu

# ─────────────────────────────────────────────────────────────────────────────
#  Cog: Painel de Configuração
#  Arquivo: cogs/mod_config.py
#
#  Comando /moderacao-config: abre um painel interativo (selects + botões)
#  pra definir canais de log, cargos de staff/mute, e os toggles gerais
#  do sistema (confirmação obrigatória, DM ao punir).
# ─────────────────────────────────────────────────────────────────────────────


def _embed_config(guild_id: int) -> discord.Embed:
    cfg = mu.get_config(guild_id)
    def canal_txt(cid):
        return f"<#{cid}>" if cid else "*não definido*"
    def cargos_txt(ids):
        return ", ".join(f"<@&{i}>" for i in ids) if ids else "*nenhum*"

    e = mu.embed_base("⚙️ Painel de Configuração — Moderação",
                       "Use os menus abaixo pra configurar o sistema. As alterações são salvas na hora.",
                       mu.COR_NEUTRO)
    e.add_field(name="📋 Canal de logs (moderação)", value=canal_txt(cfg["canal_logs_mod"]), inline=False)
    e.add_field(name="🛡️ Canal de logs (AutoMod)", value=canal_txt(cfg["canal_logs_automod"]), inline=False)
    e.add_field(name="🚨 Canal de logs (Anti-Raid)", value=canal_txt(cfg["canal_logs_antiraid"]), inline=False)
    e.add_field(name="👮 Cargos de Staff", value=cargos_txt(cfg["cargos_staff"]), inline=False)
    e.add_field(name="🔇 Cargo de Mute (backup)", value=(f"<@&{cfg['cargo_mute']}>" if cfg["cargo_mute"] else "*não definido*"), inline=False)
    e.add_field(name="✉️ Avisar punição via DM", value=("✅ Ativado" if cfg["dm_ao_punir"] else "❌ Desativado"), inline=True)
    e.add_field(name="⚠️ Exigir confirmação em ações perigosas", value=("✅ Ativado" if cfg["exigir_confirmacao"] else "❌ Desativado"), inline=True)
    return e


class PainelConfigView(discord.ui.View):
    def __init__(self, guild_id: int, autor_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.autor_id = autor_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Só quem abriu o painel (ou um admin) pode usá-lo.", ephemeral=True)
            return False
        return True

    async def _atualizar(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_embed_config(self.guild_id), view=self)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📋 Canal de logs — Moderação",
                        channel_types=[discord.ChannelType.text], row=0)
    async def canal_logs_mod(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        mu.atualizar_config(self.guild_id, canal_logs_mod=select.values[0].id)
        await self._atualizar(interaction)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="🛡️ Canal de logs — AutoMod",
                        channel_types=[discord.ChannelType.text], row=1)
    async def canal_logs_automod(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        mu.atualizar_config(self.guild_id, canal_logs_automod=select.values[0].id)
        await self._atualizar(interaction)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="🚨 Canal de logs — Anti-Raid",
                        channel_types=[discord.ChannelType.text], row=2)
    async def canal_logs_antiraid(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        mu.atualizar_config(self.guild_id, canal_logs_antiraid=select.values[0].id)
        await self._atualizar(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="👮 Cargos de Staff (múltiplo)",
                        max_values=10, row=3)
    async def cargos_staff(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        mu.atualizar_config(self.guild_id, cargos_staff=[r.id for r in select.values])
        await self._atualizar(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🔇 Cargo de Mute (backup)", row=4)
    async def cargo_mute(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        mu.atualizar_config(self.guild_id, cargo_mute=select.values[0].id)
        await self._atualizar(interaction)

    @discord.ui.button(label="Alternar DM ao punir", style=discord.ButtonStyle.secondary, emoji="✉️", row=5)
    async def toggle_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = mu.get_config(self.guild_id)
        mu.atualizar_config(self.guild_id, dm_ao_punir=not cfg["dm_ao_punir"])
        await self._atualizar(interaction)

    @discord.ui.button(label="Alternar confirmação obrigatória", style=discord.ButtonStyle.secondary, emoji="⚠️", row=5)
    async def toggle_confirmacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = mu.get_config(self.guild_id)
        mu.atualizar_config(self.guild_id, exigir_confirmacao=not cfg["exigir_confirmacao"])
        await self._atualizar(interaction)

    @discord.ui.button(label="Fechar painel", style=discord.ButtonStyle.danger, emoji="✖️", row=5)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class ModConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="moderacao-config", description="Abre o painel de configuração do sistema de moderação.")
    @app_commands.default_permissions(administrator=True)
    async def moderacao_config(self, interaction: discord.Interaction):
        view = PainelConfigView(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=_embed_config(interaction.guild_id), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModConfig(bot))
