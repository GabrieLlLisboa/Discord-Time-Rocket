import os
import sys
import subprocess

import discord
from discord.ext import commands, tasks

# ─────────────────────────────────────────────
#  Cog: Auto Update
#  Arquivo: cogs/auto_update.py
#
#  Fica de olho no commit atual do repositório (git rev-parse HEAD).
#  Quando você der `git pull` e um commit novo aparecer, o bot detecta
#  sozinho e se reinicia (mesmo processo, mesmo terminal/screen/tmux —
#  não precisa de systemd nem de nada externo).
# ─────────────────────────────────────────────

# Raiz do repositório = pasta que contém a pasta "cogs"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INTERVALO_CHECAGEM_SEGUNDOS = 60

# Canal onde o bot avisa antes de reiniciar (deixe None pra desativar o aviso)
LOG_CHANNEL_ID = 1521897698419019907

# Único usuário que pode rodar o !checarupdate manualmente
IDS_AUTORIZADOS = {1487452210605588592, 1421693641184772147}


def _commit_atual() -> str | None:
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return resultado.stdout.strip()
    except Exception as e:
        print(f"[AUTO-UPDATE] ⚠️  Não consegui checar o git (rodando fora de um repositório git?): {e}")
        return None


class AutoUpdate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.commit_atual = _commit_atual()
        if self.commit_atual:
            print(f"[AUTO-UPDATE] ✅ Monitorando commits — atual: {self.commit_atual[:7]}")
            self.checar_atualizacao.start()
        else:
            print("[AUTO-UPDATE] ⚠️  Auto-update desativado (não achei um repositório git aqui).")

    def cog_unload(self):
        self.checar_atualizacao.cancel()

    # ── Loop que checa se o HEAD mudou ───────────────────────────
    @tasks.loop(seconds=INTERVALO_CHECAGEM_SEGUNDOS)
    async def checar_atualizacao(self):
        await self.bot.wait_until_ready()
        novo = _commit_atual()
        if novo is None or novo == self.commit_atual:
            return

        antigo = self.commit_atual
        print(f"[AUTO-UPDATE] 🔄 Novo commit detectado ({antigo[:7]} → {novo[:7]}). Reiniciando o bot...")

        if LOG_CHANNEL_ID:
            canal = self.bot.get_channel(LOG_CHANNEL_ID)
            if canal is not None:
                try:
                    await canal.send(
                        f"🔄 **Nova versão detectada** (`{antigo[:7]}` → `{novo[:7]}`). Reiniciando o bot..."
                    )
                except discord.HTTPException:
                    pass

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

        novo = _commit_atual()
        if novo is None:
            await ctx.send("⚠️ Não consegui checar o git (esse diretório não parece ser um repositório).", delete_after=8)
            return

        if novo == self.commit_atual:
            await ctx.send(f"✅ Já está na última versão (`{novo[:7]}`). Nada pra atualizar.", delete_after=8)
            return

        await ctx.send(f"🔄 Detectei `{novo[:7]}` (atual: `{self.commit_atual[:7]}`). Reiniciando agora...")
        await self._reiniciar()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoUpdate(bot))
