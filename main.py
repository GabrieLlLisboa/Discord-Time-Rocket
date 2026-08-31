import importlib.util
import os
import subprocess
import sys


def _garantir_dependencias():
    """Confere se tudo que está em requirements.txt já está instalado ANTES
    de importar discord/dotenv/etc. Se faltar algo (ex: alguém deu 'git pull'
    e um requirement novo entrou, ou o venv foi criado do zero), instala tudo
    sozinho — presume que já está rodando dentro do venv certo, então usa o
    mesmo python/pip do processo atual (sys.executable)."""
    raiz = os.path.dirname(os.path.abspath(__file__))
    caminho_requirements = os.path.join(raiz, "requirements.txt")
    if not os.path.isfile(caminho_requirements):
        return


    MAPA_NOMES = {
        "discord.py": "discord",
        "python-dotenv": "dotenv",
        "pillow": "PIL",
    }

    faltando = []
    with open(caminho_requirements, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            nome_pacote = linha.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
            nome_modulo = MAPA_NOMES.get(nome_pacote.lower(), nome_pacote.replace("-", "_"))
            try:
                encontrado = importlib.util.find_spec(nome_modulo) is not None
            except (ImportError, ValueError, ModuleNotFoundError):
                encontrado = False
            if not encontrado:
                faltando.append(linha)

    if not faltando:
        return

    print(f"[SETUP] ⚠️ Dependência(s) faltando no venv: {', '.join(faltando)}")
    print("[SETUP] 📦 Instalando tudo do requirements.txt automaticamente...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", caminho_requirements],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[SETUP] ❌ Falha ao instalar dependências automaticamente: {e}")
        print("[SETUP]    Roda manualmente: pip install -r requirements.txt")
        raise SystemExit(1)

    importlib.invalidate_caches()
    print("[SETUP] ✅ Dependências instaladas. Continuando a inicialização...")


_garantir_dependencias()

import asyncio
import inspect

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.mod_utils import SUPER_ADMIN_IDS, eh_super_admin_membro

load_dotenv()
TOKEN    = os.getenv("DISCORD_TOKEN")
PREFIX   = os.getenv("PREFIX", "!")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.members         = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


@bot.before_invoke
async def apagar_mensagem_do_comando(ctx: commands.Context):
    """Roda antes de QUALQUER comando de prefixo (!setup, !clear, etc).
    Apaga a mensagem de quem digitou o comando, pra manter o canal limpo,
    sem precisar repetir 'ctx.message.delete()' em cada cog.

    Só chega até aqui depois que os checks de permissão passaram, então um
    comando negado por falta de permissão não apaga a mensagem (o autor
    ainda vê o próprio comando e o aviso de erro)."""
    if ctx.guild is None:

        return
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    import traceback


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
    "cogs.mais_ativo",
    "cogs.campeonato",
    "cogs.campeonato_partida",
    "cogs.logs",
    "cogs.convites",
    "cogs.whitelist",
    "cogs.staff_tag",
    "cogs.cargo_equipe_auto",
    "cogs.enquete",
    "cogs.auto_update",
    "cogs.demote",
    "cogs.coach_commands",
    "cogs.tradutor",
    "cogs.quiz",
    "cogs.autopilot",
    "cogs.conversar",
    "cogs.aleatory",
    "cogs.webterminal",

    "cogs.perfil_gestao",
    "cogs.emprestimo",
    "cogs.ranking",
    "cogs.disponibilidade",
    "cogs.anunciar",


    "cogs.mod_config",
    "cogs.mod_setup",
    "cogs.moderation",
    "cogs.automod",
    "cogs.antiraid",
    "cogs.antinuke",
    "cogs.clear",
]

async def _resultado_check(check, ctx_ou_interaction):
    """Executa um check (síncrono ou assíncrono) e retorna o bool resultante."""
    resultado = check(ctx_ou_interaction)
    if inspect.isawaitable(resultado):
        resultado = await resultado
    return resultado


def liberar_super_admins():
    """
    Dá acesso total a TODOS os comandos do bot (prefixo e slash), em
    qualquer servidor, para os IDs listados em mod_utils.SUPER_ADMIN_IDS —
    sem precisar de cargo/permissão nenhuma no Discord.

    Funciona envolvendo a lista de checks de cada comando (@commands.has_
    permissions, @commands.has_role, @app_commands.checks.has_permissions,
    @app_commands.checks.has_any_role, etc.) numa checagem única: se quem
    executou é super admin, libera na hora; senão, roda os checks originais
    normalmente. Precisa ser chamado DEPOIS de todos os cogs carregados.

    OBS: comandos com @app_commands.default_permissions(...) (ex.: os grupos
    /antinuke, /antiraid, /automod-setup e o /moderacao-config) usam uma
    restrição do próprio Discord — o Discord só deixa o usuário nem abrir o
    comando se ele não tiver aquela permissão na conta dele no servidor,
    então isso não dá pra liberar só por código. Pra esses, garanta que o
    super admin tenha um cargo com a permissão pedida (ex.: Administrador)
    OU libere manualmente em Configurações do Servidor → Integrações →
    TryHarders RL Bot → permissões do comando.
    """

    for command in bot.walk_commands():
        checks_originais = list(command.checks)
        if not checks_originais:
            continue

        async def _check_liberado(ctx, _checks=checks_originais):
            if eh_super_admin_membro(ctx.author):
                return True
            for check in _checks:
                if not await _resultado_check(check, ctx):
                    return False
            return True

        command.checks = [_check_liberado]


    for command in bot.tree.walk_commands():
        if not isinstance(command, discord.app_commands.Command):


            continue
        checks_originais = list(command.checks)
        if not checks_originais:
            continue

        async def _check_liberado_slash(interaction, _checks=checks_originais):
            if eh_super_admin_membro(interaction.user):
                return True
            for check in _checks:
                if not await _resultado_check(check, interaction):
                    return False
            return True

        command.checks = [_check_liberado_slash]

    print(f"[PERMS] ✅ Super admin(s) liberado(s) para todos os comandos: {sorted(SUPER_ADMIN_IDS)}")


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
    from cogs.tickets import TicketSetupView, FecharTicketView, ReabrirTicketView, ForcarExclusaoView, AbrirTicketDevView
    from cogs.notifications import NotificacaoView
    from cogs.tracker import TrackerView
    from cogs.welcome import BoasVindasView
    from cogs.whitelist import ComecarWhitelistView, FinalizarWhitelistView
    from cogs.atividade import SetupAtividadeView


    bot.add_view(TicketSetupView())
    bot.add_view(FecharTicketView())
    bot.add_view(ReabrirTicketView())
    bot.add_view(ForcarExclusaoView())
    bot.add_view(AbrirTicketDevView())
    bot.add_view(NotificacaoView())
    bot.add_view(TrackerView())
    bot.add_view(BoasVindasView())
    bot.add_view(ComecarWhitelistView())
    bot.add_view(FinalizarWhitelistView())
    bot.add_view(SetupAtividadeView())


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


    try:
        from cogs.coach_config import COACHES
        from cogs.coach_views import ComprarAtendimentoView, AvaliarCoachView, CancelarCoachView
        from cogs.coach_storage import listar_tickets_para_reavaliacao, listar_tickets_em_andamento

        for coach_key in COACHES:
            bot.add_view(ComprarAtendimentoView(coach_key))

        tickets_pendentes = await listar_tickets_para_reavaliacao()
        for ticket in tickets_pendentes:
            bot.add_view(AvaliarCoachView(ticket["canal_ticket_id"]))

        tickets_em_andamento = await listar_tickets_em_andamento()
        for ticket in tickets_em_andamento:
            bot.add_view(CancelarCoachView(ticket["canal_ticket_id"]))

        print(
            f"[VIEWS] ✅ {len(COACHES)} view(s) de coach(es), "
            f"{len(tickets_em_andamento)} view(s) de cancelamento pendente(s) e "
            f"{len(tickets_pendentes)} view(s) de avaliação pendente(s) recarregada(s)."
        )
    except Exception as e:
        print(f"[VIEWS] ⚠️  Erro ao recarregar views do sistema de coaches: {e}")

    print("[VIEWS] ✅ Views persistentes registradas.")


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
        liberar_super_admins()
        await registrar_views_persistentes()
        asyncio.create_task(iniciar_console(bot))
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
