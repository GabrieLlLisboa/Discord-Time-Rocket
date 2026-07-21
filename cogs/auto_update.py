import asyncio
import os
import sys
import subprocess

import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────
#  Cog: Auto Update
#  Arquivo: cogs/auto_update.py
#
#  A cada 10s, dá um `git fetch` e compara o commit local com o commit da
#  branch remota (a que o `git pull` normal usaria). Se tiver algo novo no
#  GitHub, puxa (`git pull`) e reinicia o bot sozinho — sem precisar rodar
#  nada manualmente no servidor, só dar `git push` na sua máquina.
# ─────────────────────────────────────────────

# Raiz do repositório = pasta que contém a pasta "cogs"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INTERVALO_CHECAGEM_SEGUNDOS = 10

# Canal onde o bot avisa antes de reiniciar (deixe None pra desativar o aviso)
LOG_CHANNEL_ID = 1529234118557306971

# Único usuário que pode rodar o !checarupdate manualmente
IDS_AUTORIZADOS = {1487452210605588592}


def _git_sync(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


async def _git(*args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Roda um comando git em outra thread (subprocess é bloqueante)."""
    return await asyncio.to_thread(_git_sync, *args, timeout=timeout)


def _repo_valido() -> bool:
    try:
        r = _git_sync("rev-parse", "HEAD", timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class AutoUpdate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if _repo_valido():
            print("[AUTO-UPDATE] ✅ Repositório git detectado — vou checar o GitHub a cada 60s.")
            self.checar_atualizacao.start()
        else:
            print("[AUTO-UPDATE] ⚠️  Auto-update desativado (essa pasta não é um repositório git).")

    def cog_unload(self):
        self.checar_atualizacao.cancel()

    # ── Descobre o commit local e o commit da branch remota (upstream) ──
    async def _commits(self):
        """Retorna (commit_local, commit_remoto) ou (None, None) se der erro."""
        fetch = await _git("fetch", "--quiet")
        if fetch.returncode != 0:
            print(f"[AUTO-UPDATE] ⚠️  'git fetch' falhou: {fetch.stderr.strip()}")
            return None, None

        local = await _git("rev-parse", "HEAD")
        remoto = await _git("rev-parse", "@{u}")  # @{u} = branch remota configurada (a que o `git pull` usaria)

        if local.returncode != 0 or remoto.returncode != 0:
            print(
                "[AUTO-UPDATE] ⚠️  Não consegui comparar com a branch remota "
                "(a branch local tem upstream configurado? rode `git branch --set-upstream-to=origin/main` no servidor)."
            )
            return None, None

        return local.stdout.strip(), remoto.stdout.strip()

    # ── Loop que checa o GitHub a cada 60s ───────────────────────
    @tasks.loop(seconds=INTERVALO_CHECAGEM_SEGUNDOS)
    async def checar_atualizacao(self):
        await self.bot.wait_until_ready()

        local, remoto = await self._commits()
        if local is None or local == remoto:
            return

        print(f"[AUTO-UPDATE] 🔄 Commit novo no GitHub detectado ({local[:7]} → {remoto[:7]}). Puxando...")

        pull = await _git("pull")
        if pull.returncode != 0:
            print(f"[AUTO-UPDATE] ❌ 'git pull' falhou, não vou reiniciar:\n{pull.stderr.strip()}")
            return

        if LOG_CHANNEL_ID:
            canal = self.bot.get_channel(LOG_CHANNEL_ID)
            if canal is not None:
                try:
                    await canal.send(
                        f"🔄 **Nova versão detectada no GitHub** (`{local[:7]}` → `{remoto[:7]}`). Reiniciando o bot..."
                    )
                except discord.HTTPException:
                    pass

        print("[AUTO-UPDATE] ✅ Atualizado! Reiniciando...")
        await self._reiniciar()

    @checar_atualizacao.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()

    # ── Reinicia o processo em pé (mesmo PID/terminal) ───────────
    async def _reiniciar(self):
        try:
            await self.bot.close()
        finally:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── !checarupdate — força a checagem na hora (staff autorizada) ─────────
    @commands.command(name="checarupdate", hidden=True)
    async def checar_update_manual(self, ctx: commands.Context):
        if ctx.author.id not in IDS_AUTORIZADOS:
            return

        msg = await ctx.send("🔎 Checando o GitHub...")

        local, remoto = await self._commits()
        if local is None:
            await msg.edit(content="⚠️ Não consegui checar (veja o console para detalhes — provavelmente falta configurar upstream/remoto).")
            return

        if local == remoto:
            await msg.edit(content=f"✅ Já está na última versão (`{local[:7]}`). Nada pra atualizar.")
            return

        await msg.edit(content=f"🔄 Detectei `{remoto[:7]}` (atual: `{local[:7]}`). Puxando e reiniciando...")
        pull = await _git("pull")
        if pull.returncode != 0:
            await msg.edit(content=f"❌ `git pull` falhou:\n```\n{pull.stderr.strip()[:1800]}\n```")
            return

        await self._reiniciar()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoUpdate(bot))
