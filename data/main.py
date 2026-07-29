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
    "cogs.backup",
    "cogs.stats",
    "cogs.treinos",
    "cogs.resultados",
]

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ {cog} carregado.")
        except Exception as e:
            print(f"[COG] ❌ Erro ao carregar {cog}: {e}")

async def registrar_views_persistentes():
    """
    Registra todas as Views com botões no bot antes do on_ready.
    Isso faz os botões funcionarem mesmo após reiniciar o bot,
    sem precisar reenviar as mensagens.
    """
    from cogs.tickets import TicketSetupView
    from cogs.notifications import NotificacaoView
    from cogs.friendly import ConfirmarPresencaView, SairAmistosoView

    # Views sem estado (não precisam de argumentos)
    bot.add_view(TicketSetupView())
    bot.add_view(NotificacaoView())
    bot.add_view(SairAmistosoView())

    # ConfirmarPresencaView precisa de rank_alvo, rank_id e canal_id
    # Recria a partir dos amistosos salvos no JSON
    try:
        from cogs.backup import ler
        amistosos = ler("amistosos")
        count = 0
        for a in amistosos:
            if a.get("resultado") is not None:
                continue  # amistoso já encerrado, ignora

            from cogs.friendly import RANKS, encontrar_rank
            rank_nome = a.get("rank", "")
            rank_id   = RANKS.get(rank_nome)
            canal_id  = a.get("canal_id")

            if rank_id and canal_id:
                bot.add_view(
                    ConfirmarPresencaView(
                        rank_alvo=rank_nome,
                        rank_id=rank_id,
                        canal_amistoso_id=canal_id,
                    )
                )
                count += 1
        if count:
            print(f"[VIEWS] ✅ {count} view(s) de amistoso(s) em aberto recarregada(s).")
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views de amistosos: {e}")

    print("[VIEWS] ✅ Views persistentes registradas.")

@bot.event
async def on_ready():
    print(f"\n{'─'*40}")
    print(f"  Bot online: {bot.user} ({bot.user.id})")
    print(f"  Prefixo: {PREFIX}")
    print(f"  Servidores: {len(bot.guilds)}")
    print(f"{'─'*40}\n")

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
        await registrar_views_persistentes()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
