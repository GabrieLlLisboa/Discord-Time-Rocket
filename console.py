import asyncio
import os
import subprocess
import sys

import discord

# ─────────────────────────────────────────────
#  Terminal de comandos do bot
#  Arquivo: console.py
#
#  Fica lendo o que você digita direto no terminal onde o bot tá rodando
#  (sem precisar do Discord) e executa ações administrativas.
#
#  Comandos disponíveis:
#    update              -> git pull + reinicia
#    reiniciar / restart -> reinicia o bot (mesmo processo)
#    desligar / shutdown -> encerra o bot de vez
#    status              -> mostra info rápida (usuário, servidores, ping)
#    ajuda / help        -> lista os comandos
# ─────────────────────────────────────────────

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

COMANDOS_AJUDA = (
    "Comandos disponíveis:\n"
    "  update              -> git pull + reinicia o bot\n"
    "  reiniciar / restart -> reinicia o bot (mesmo processo)\n"
    "  desligar / shutdown -> encerra o bot de vez\n"
    "  status              -> mostra usuário, servidores e ping\n"
    "  ajuda / help        -> mostra essa lista"
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


async def iniciar_console(bot: discord.Client):
    """Inicia o loop que lê comandos digitados no terminal. Roda em paralelo com o bot."""
    if not sys.stdin or not sys.stdin.isatty():
        # Sem terminal interativo de verdade (ex: rodando via nohup/serviço sem tty)
        # — não adianta ficar lendo stdin, então nem inicia.
        print("[CONSOLE] ℹ️  Sem terminal interativo detectado, comandos de console desativados.")
        return

    print("[CONSOLE] 💻 Terminal de comandos ativo. Digite 'ajuda' pra ver os comandos.")

    while True:
        linha = await asyncio.to_thread(sys.stdin.readline)
        if not linha:
            # EOF (ex: terminal fechou) — evita loop infinito consumindo CPU
            await asyncio.sleep(1)
            continue

        comando = linha.strip().lower()
        if not comando:
            continue

        if comando in ("ajuda", "help"):
            print(f"[CONSOLE] {COMANDOS_AJUDA}")

        elif comando in ("status",):
            latencia = round(bot.latency * 1000) if bot.latency else "?"
            print(f"[CONSOLE] ✅ Online como {bot.user} | {len(bot.guilds)} servidor(es) | ping {latencia}ms")

        elif comando in ("desligar", "shutdown", "sair", "exit"):
            print("[CONSOLE] 🛑 Desligando o bot...")
            await bot.close()
            returns

        elif comando in ("down", "restart"):
            print("[CONSOLE] 🔄 Reiniciando o bot...")
            await bot.close()
            _reiniciar_processo()

        elif comando in ("up", "atualizar"):
            print("[CONSOLE] ⬇️  Rodando 'git pull'...")
            sucesso, saida = await _rodar_git_pull()
            if saida:
                print(f"[CONSOLE] {saida}")
            if not sucesso:
                print("[CONSOLE] ❌ 'git pull' falhou — não vou reiniciar. Resolve o problema (ex: conflito) e tenta de novo.")
                continue
            if "Already up to date" in saida or "já está atualizado" in saida.lower():
                print("[CONSOLE] ✅ Já estava atualizado, nada pra reiniciar.")
                continue
            print("[CONSOLE] 🔄 Atualizado! Reiniciando pra aplicar...")
            await bot.close()
            _reiniciar_processo()

        else:
            print(f"[CONSOLE] ❓ Comando desconhecido: '{comando}'. Digite 'ajuda' pra ver os comandos.")
