import asyncio
import os
import sys

import discord

from update_lock import LOCK
from git_utils import pull_com_recuperacao_sync


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

COMANDOS_AJUDA = (
    "Comandos disponíveis:\n"
    "  update                        -> git pull, espera 2s e reinicia o bot\n"
    "  reiniciar / restart           -> reinicia o bot (mesmo processo)\n"
    "  parar / desligar / shutdown   -> encerra o bot de vez\n"
    "  status                        -> mostra usuário, servidores e ping\n"
    "  ajuda / help                  -> mostra essa lista"
)


def _reiniciar_processo():
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def _rodar_git_pull() -> tuple[bool, str, bool]:
    """Roda git pull (com recuperação automática se der conflito de mudança
    local) em outra thread, já que subprocess é bloqueante."""
    try:
        return await asyncio.to_thread(pull_com_recuperacao_sync, REPO_ROOT)
    except Exception as e:
        return False, str(e), False


async def _antes_de_matar_o_processo():
    """Dá um respiro pro cog do terminal web mandar as últimas linhas pro
    canal do Discord antes do processo fechar (bot.close()) ou reiniciar
    (os.execv, que substitui o processo na hora)."""
    try:
        from cogs.webterminal import forcar_flush
        await forcar_flush()
    except Exception:
        pass
    await asyncio.sleep(0.3)


async def cmd_status(bot: discord.Client):
    latencia = round(bot.latency * 1000) if bot.latency else "?"
    print(f"[CONSOLE] ✅ Online como {bot.user} | {len(bot.guilds)} servidor(es) | ping {latencia}ms")


async def cmd_desligar(bot: discord.Client):
    print("[CONSOLE] 🛑 Desligando o bot...")
    await _antes_de_matar_o_processo()
    await bot.close()


async def cmd_reiniciar(bot: discord.Client):
    print("[CONSOLE] 🔄 Reiniciando o bot...")
    await _antes_de_matar_o_processo()
    _reiniciar_processo()


async def cmd_update(bot: discord.Client):
    if LOCK.locked():
        print("[CONSOLE] ⏳ Já tem uma atualização rolando (provavelmente o auto-update). Espera terminar e tenta de novo.")
        return

    async with LOCK:
        print("[CONSOLE] ⬇️  Rodando 'git pull'...")
        sucesso, saida, recuperou = await _rodar_git_pull()
        if saida:
            print(f"[CONSOLE] {saida}")

        if not sucesso:
            print("[CONSOLE] ❌ 'git pull' falhou — não vou reiniciar. Resolve o problema (ex: conflito) e tenta de novo.")
            return

        if recuperou:
            print("[CONSOLE] 🩹 O pull tinha travado por causa de mudanças locais, mas eu resolvi sozinho com 'git reset --hard'.")

        if not recuperou and ("Already up to date" in saida or "já está atualizado" in saida.lower()):
            print("[CONSOLE] ✅ Já estava atualizado, nada pra reiniciar.")
            return

        print("[CONSOLE] 🔄 Atualizado! Esperando 2 segundos antes de reiniciar...")
        await asyncio.sleep(2)
        print("[CONSOLE] 🔄 Reiniciando pra aplicar as mudanças...")
        await _antes_de_matar_o_processo()
        _reiniciar_processo()


async def executar_comando(bot: discord.Client, comando: str) -> bool:
    """Executa um comando de console. Usado tanto pelo terminal local quanto
    pelo canal 'web terminal' no Discord (cogs/webterminal.py).
    Retorna True se o comando foi reconhecido (mesmo que tenha falhado),
    False se for um comando desconhecido."""
    comando = comando.strip().lower()

    if comando in ("ajuda", "help"):
        print(f"[CONSOLE] {COMANDOS_AJUDA}")
    elif comando == "status":
        await cmd_status(bot)
    elif comando in ("parar", "desligar", "shutdown", "sair", "exit"):
        await cmd_desligar(bot)
    elif comando in ("reiniciar", "restart"):
        await cmd_reiniciar(bot)
    elif comando in ("update", "atualizar"):
        await cmd_update(bot)
    else:
        return False
    return True


async def iniciar_console(bot: discord.Client):
    """Inicia o loop que lê comandos digitados no terminal. Roda em paralelo com o bot."""
    if not sys.stdin or not sys.stdin.isatty():


        print("[CONSOLE] ℹ️  Sem terminal interativo detectado, comandos de console desativados.")
        return

    print("[CONSOLE] 💻 Terminal de comandos ativo. Digite 'ajuda' pra ver os comandos.")

    while True:
        linha = await asyncio.to_thread(sys.stdin.readline)
        if not linha:

            await asyncio.sleep(1)
            continue

        comando = linha.strip()
        if not comando:
            continue

        conhecido = await executar_comando(bot, comando)
        if not conhecido:
            print(f"[CONSOLE] ❓ Comando desconhecido: '{comando}'. Digite 'ajuda' pra ver os comandos.")
