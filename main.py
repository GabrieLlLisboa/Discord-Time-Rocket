import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN    = os.getenv("DISCORD_TOKEN")
PREFIX   = os.getenv("PREFIX", "!")
GUILD_ID = os.getenv("GUILD_ID")  # opcional — se preencher, sincroniza slash commands na hora nesse servidor

intents = discord.Intents.default()
intents.members         = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    import traceback

    # Loga o erro completo no console (é aqui que dá pra ver a causa real)
    print(f"[SLASH] ❌ Erro no comando '/{interaction.command.name if interaction.command else '?'}':")
    traceback.print_exception(type(error), error, error.__traceback__)

    mensagem = "❌ Deu erro ao executar esse comando. A staff já foi avisada (olha o console)."
    if isinstance(error, discord.app_commands.MissingPermissions):
        mensagem = "❌ Você não tem permissão pra usar esse comando."
    elif isinstance(error, discord.app_commands.CommandOnCooldown):
        mensagem = f"⏳ Calma, tenta de novo em {error.retry_after:.0f}s."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)
    except discord.HTTPException:
        pass

COGS = [
    "cogs.welcome",
    "cogs.leave",
    "cogs.tickets",
    "cogs.notifications",
    "cogs.players",
    "cogs.friendly",
    "cogs.tiktok",
    "cogs.backup",
    "cogs.stats",
    "cogs.treinos",
    "cogs.resultados",
    "cogs.tracker",
    "cogs.atividade",
    "cogs.campeonato",
    "cogs.logs",
    "cogs.convites",
    "cogs.whitelist",
    "cogs.staff_tag",
    "cogs.enquete",
    "cogs.auto_update",
    "cogs.demote",
    "cogs.coach_commands",
    "cogs.tradutor",
    "cogs.quiz",
    "cogs.autopilot",

    # ── Sistema de Moderação ──
    "cogs.mod_config",
    "cogs.mod_setup",
    "cogs.moderation",
    "cogs.automod",
    "cogs.antiraid",
    "cogs.clear",
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

    OBS: as views do sistema de amistoso (SairAmistosoView e
    ConfirmarPresencaView) NÃO são registradas aqui — o cog
    cogs/friendly.py já cuida disso sozinho, no Friendly.__init__,
    de um jeito mais correto (por mensagem, com o rank/canal certo de
    cada amistoso). Registrar de novo aqui rodaria DEPOIS de load_cogs()
    e SOBRESCREVERIA esse registro com uma versão antiga que juntava
    todos os amistosos abertos numa view "global" só — quebrando os
    botões de confirmar presença quando houvesse 2+ amistosos abertos
    ao mesmo tempo.
    """
    from cogs.tickets import TicketSetupView
    from cogs.notifications import NotificacaoView
    from cogs.tracker import TrackerView
    from cogs.welcome import BoasVindasView
    from cogs.whitelist import ComecarWhitelistView, FinalizarWhitelistView
    from cogs.atividade import SetupAtividadeView

    # Views sem estado (não precisam de argumentos)
    bot.add_view(TicketSetupView())
    bot.add_view(NotificacaoView())
    bot.add_view(TrackerView())
    bot.add_view(BoasVindasView())
    bot.add_view(ComecarWhitelistView())
    bot.add_view(FinalizarWhitelistView())
    bot.add_view(SetupAtividadeView())

    # Views de campeonatos em aberto (o botão "Entrar no Torneio" precisa
    # ser recriado com o custom_id certo pra continuar funcionando)
    try:
        from cogs.campeonato import EntrarTorneioView, ler_campeonatos
        campeonatos = ler_campeonatos()
        count = 0
        for chave, info in campeonatos.items():
            fechado = not info.get("inscricoes_abertas", True)
            bot.add_view(EntrarTorneioView(chave, fechado=fechado))
            count += 1
        if count:
            print(f"[VIEWS] ✅ {count} view(s) de campeonato(s) recarregada(s).")
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views de campeonatos: {e}")

    # Sistema de Coaches: um botão "Comprar Atendimento" por coach + um
    # botão "Avaliar Coach" para cada ticket já finalizado mas ainda sem
    # avaliação (senão o botão pararia de funcionar após um restart).
    try:
        from cogs.coach_config import COACHES
        from cogs.coach_views import ComprarAtendimentoView, AvaliarCoachView
        from cogs.coach_storage import listar_tickets_para_reavaliacao

        for coach_key in COACHES:
            bot.add_view(ComprarAtendimentoView(coach_key))

        tickets_pendentes = await listar_tickets_para_reavaliacao()
        for ticket in tickets_pendentes:
            bot.add_view(AvaliarCoachView(ticket["canal_ticket_id"]))

        print(
            f"[VIEWS] ✅ {len(COACHES)} view(s) de coach(es) e "
            f"{len(tickets_pendentes)} view(s) de avaliação pendente(s) recarregada(s)."
        )
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views do sistema de coaches: {e}")

    print("[VIEWS] ✅ Views persistentes registradas.")

    # Whitelists pendentes/em análise: recria os botões de revisão
    try:
        from cogs.whitelist import RevisaoWhitelistView
        from cogs.backup import ler as ler_backup
        whitelist_dados = ler_backup("whitelist")
        count = 0
        for uid_str, registro in whitelist_dados.items():
            if registro.get("status") in ("pendente", "visualizada"):
                bot.add_view(RevisaoWhitelistView(int(uid_str)))
                count += 1
        if count:
            print(f"[VIEWS] ✅ {count} view(s) de revisão de whitelist recarregada(s).")
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views de whitelist: {e}")

    # Enquetes abertas: recria os botões de voto/encerrar
    try:
        from cogs.enquete import EnqueteView
        from cogs.backup import ler as ler_backup
        enquetes_dados = ler_backup("enquetes")
        count = 0
        for poll_id, registro in enquetes_dados.items():
            bot.add_view(EnqueteView(
                poll_id,
                registro["opcoes"],
                aberta=registro.get("aberta", True),
                anonima=registro.get("anonima", False),
            ))
            count += 1
        if count:
            print(f"[VIEWS] ✅ {count} enquete(s) recarregada(s).")
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views de enquetes: {e}")

_pronto_uma_vez = False


@bot.event
async def on_ready():
    global _pronto_uma_vez
    print(f"\n{'─'*40}")
    print(f"  Bot online: {bot.user} ({bot.user.id})")
    print(f"  Prefixo: {PREFIX}")
    print(f"  Servidores: {len(bot.guilds)}")
    print(f"{'─'*40}\n")

    # on_ready pode disparar mais de uma vez no mesmo processo (ex: o bot
    # perde e recupera a conexão com o Discord — RESUME/reconnect). Sincronizar
    # os slash commands globais toda vez que isso acontece é desnecessário e
    # arriscado: syncs repetidos em pouco tempo podem esbarrar em rate limit
    # da API do Discord. Por isso só sincronizamos na primeira vez.
    if not _pronto_uma_vez:
        _pronto_uma_vez = True
        try:
            synced = await bot.tree.sync()
            print(f"[SLASH] ✅ {len(synced)} comando(s) global(is) sincronizado(s) (pode levar até 1h pra aparecer em todo lugar).")

            if GUILD_ID:
                guild_obj = discord.Object(id=int(GUILD_ID))
                bot.tree.copy_global_to(guild=guild_obj)
                synced_guild = await bot.tree.sync(guild=guild_obj)
                print(f"[SLASH] ✅ {len(synced_guild)} comando(s) sincronizado(s) na hora no servidor {GUILD_ID}.")
        except Exception as e:
            print(f"[SLASH] ❌ Erro ao sincronizar: {e}")

    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="TryHarders RL"
            )
        )
    except discord.HTTPException:
        pass

async def main():
    if not TOKEN:
        raise SystemExit(
            "[FATAL] ❌ A variável de ambiente DISCORD_TOKEN não foi definida.\n"
            "         Crie um arquivo .env na raiz do projeto com a linha:\n"
            "         DISCORD_TOKEN=seu_token_aqui"
        )

    from console import iniciar_console
    async with bot:
        await load_cogs()
        await registrar_views_persistentes()
        asyncio.create_task(iniciar_console(bot))
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
