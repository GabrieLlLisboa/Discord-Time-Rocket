import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN  = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

intents = discord.Intents.default()
intents.members         = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

COGS = [
    "cogs.welcome",
    "cogs.tickets",
    "cogs.clear",
    "cogs.notifications",
    "cogs.players",
    "cogs.friendly",
    "cogs.tiktok",
]

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ {cog} carregado.")
        except Exception as e:
            print(f"[COG] ❌ Erro ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    print(f"\n{'─'*40}")
    print(f"  Bot online: {bot.user} ({bot.user.id})")
    print(f"  Prefixo: {PREFIX}")
    print(f"  Servidores: {len(bot.guilds)}")
    print(f"{'─'*40}\n")

    # Sincroniza slash commands globalmente
    try:
        synced = await bot.tree.sync()
        print(f"[SLASH] ✅ {len(synced)} comando(s) sincronizado(s).")
    except Exception as e:
        print(f"[SLASH] ❌ Erro ao sincronizar: {e}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="TryHarders RL"
        )
    )

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
