import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Backup Automático
#  Arquivo: cogs/backup.py
#  Salva dados a cada 6 horas em /data/
# ─────────────────────────────────────────────

DATA_DIR = "data"

# Arquivos de dados
FILES = {
    "amistosos":   "data/amistosos.json",
    "resultados":  "data/resultados.json",
    "perfis":      "data/perfis.json",
    "treinos":     "data/treinos.json",
}

os.makedirs(DATA_DIR, exist_ok=True)


# ── Helpers de leitura/escrita ─────────────────────────────────────────────────
def ler(chave: str) -> dict | list:
    path = FILES[chave]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Valor padrão por chave
    return [] if chave in ("amistosos", "treinos") else {}


def salvar(chave: str, dados):
    path = FILES[chave]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def agora_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


# ── Cog ───────────────────────────────────────────────────────────────────────
class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Garante que todos os arquivos existem
        for chave in FILES:
            if not os.path.exists(FILES[chave]):
                salvar(chave, ler(chave))
        self.backup_loop.start()

    def cog_unload(self):
        self.backup_loop.cancel()

    @tasks.loop(hours=6)
    async def backup_loop(self):
        await self.bot.wait_until_ready()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        backup_dir = f"data/backups/{timestamp}"
        os.makedirs(backup_dir, exist_ok=True)

        for chave, path in FILES.items():
            if os.path.exists(path):
                dados = ler(chave)
                backup_path = f"{backup_dir}/{chave}.json"
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)

        # Mantém apenas os últimos 10 backups
        backups = sorted(os.listdir("data/backups"))
        while len(backups) > 10:
            import shutil
            shutil.rmtree(f"data/backups/{backups.pop(0)}")

        print(f"[BACKUP] ✅ Backup realizado em {backup_dir}")

    @backup_loop.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
