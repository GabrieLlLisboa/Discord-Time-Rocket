"""Isolamento do servidor de Minecraft.

O MESMO bot roda nos dois servidores, mas no de Minecraft só funcionam as cogs
`McWhitelist` e `McSetup` (cogs/mc_whitelist.py e cogs/mc_setup.py). Todo o resto
(welcome, tickets, logs, antiraid, players, ...) fica "cego" pra esse servidor:

  1. eventos     -> listeners de outras cogs não são disparados com eventos de lá
  2. comandos !  -> no servidor de Minecraft só os comandos das cogs Mc* funcionam
                    (e os comandos Mc* só funcionam lá)
  3. comandos /  -> bloqueados no servidor de Minecraft
  4. bot.guilds  -> não lista o servidor de Minecraft, então os loops das outras cogs
                    (`for guild in self.bot.guilds`) nem passam por lá

Nenhuma cog do Rocket foi alterada.
"""
import discord
from discord import app_commands
from discord.ext import commands

from cogs import mc_config as cfg

COGS_MINECRAFT = {"McWhitelist", "McSetup"}


class ComandoBloqueado(commands.CheckFailure, app_commands.CheckFailure):
    """Comando usado no servidor errado (silencioso: não gera traceback)."""


def guild_id_do_evento(args) -> int | None:
    """Descobre de qual servidor é um evento do discord.py, olhando os argumentos."""
    for a in args:
        if isinstance(a, discord.Guild):
            return a.id
        gid = getattr(a, "guild_id", None)  # payloads raw e interactions
        if gid:
            return gid
        guild = getattr(a, "guild", None)  # Member, Message, canais, cargos, convites...
        if guild is not None and getattr(guild, "id", None):
            return guild.id
        for ponte in ("channel", "message"):  # VoiceState, Reaction
            objeto = getattr(a, ponte, None)
            guild = getattr(objeto, "guild", None)
            if guild is not None and getattr(guild, "id", None):
                return guild.id
    return None


class BotIsolado(commands.Bot):
    @property
    def guilds(self):
        mc = cfg.guild_id()
        return [g for g in super().guilds if g.id != mc]

    def _schedule_event(self, coro, event_name, *args, **kwargs):
        dono = getattr(coro, "__self__", None)
        if (
            isinstance(dono, commands.Cog)
            and dono.qualified_name not in COGS_MINECRAFT
            and guild_id_do_evento(args) == cfg.guild_id()
        ):
            return None  # evento do servidor de Minecraft: só as cogs Mc* recebem
        return super()._schedule_event(coro, event_name, *args, **kwargs)

    async def on_command_error(self, ctx, error):
        if isinstance(error, ComandoBloqueado):
            return
        await super().on_command_error(ctx, error)


def instalar_isolamento(bot: BotIsolado) -> None:
    @bot.check
    async def _escopo_comandos_prefixo(ctx: commands.Context) -> bool:
        no_minecraft = ctx.guild is not None and ctx.guild.id == cfg.guild_id()
        cog = ctx.command.cog if ctx.command else None
        eh_minecraft = cog is not None and cog.qualified_name in COGS_MINECRAFT
        if no_minecraft != eh_minecraft:
            raise ComandoBloqueado()
        return True

    async def _escopo_comandos_slash(interaction: discord.Interaction) -> bool:
        if interaction.guild_id == cfg.guild_id():
            raise ComandoBloqueado()
        return True

    bot.tree.interaction_check = _escopo_comandos_slash
