import asyncio
import os
import subprocess
import sys

import discord


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


async def _rodar_git_pull() -> tuple[bool, str]:
    """Roda git pull em outra thread (é bloqueante) e retorna (sucesso, saida)."""
    def _executar():
        return subprocess.run(
            ["git", "pull"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )

    try:
        resultado = await asyncio.to_thread(_executar)
    except Exception as e:
        return False, str(e)

    saida = (resultado.stdout or "") + (resultado.stderr or "")
    return resultado.returncode == 0, saida.strip()


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
    await bot.close()
    _reiniciar_processo()


async def cmd_update(bot: discord.Client):
    print("[CONSOLE] ⬇️  Rodando 'git pull'...")
    sucesso, saida = await _rodar_git_pull()
    if saida:
        print(f"[CONSOLE] {saida}")

    if not sucesso:
        print("[CONSOLE] ❌ 'git pull' falhou — não vou reiniciar. Resolve o problema (ex: conflito) e tenta de novo.")
        return

    if "Already up to date" in saida or "já está atualizado" in saida.lower():
        print("[CONSOLE] ✅ Já estava atualizado, nada pra reiniciar.")
        return

    print("[CONSOLE] 🔄 Atualizado! Esperando 2 segundos antes de reiniciar...")
    await asyncio.sleep(2)
    print("[CONSOLE] 🔄 Reiniciando pra aplicar as mudanças...")
    await _antes_de_matar_o_processo()
    await bot.close()
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
