from discord.ext import commands, tasks
import os
import shutil
from datetime import datetime, timezone

from cogs.json_store import ler_json, salvar_json


DATA_DIR = "data"


FILES = {
    "amistosos":    "data/amistosos.json",
    "resultados":   "data/resultados.json",
    "perfis":       "data/perfis.json",
    "treinos":      "data/treinos.json",
    "demotados":    "data/demotados.json",
    "whitelist":    "data/whitelist.json",
    "enquetes":     "data/enquetes.json",


    "campeonatos":  "data/campeonatos.json",
    "partidas_campeonato": "data/partidas_campeonato.json",

    "emprestimos":      "data/emprestimos.json",
    "disponibilidade":  "data/disponibilidade.json",
    "anuncios_config":  "data/anuncios_config.json",
}

os.makedirs(DATA_DIR, exist_ok=True)


def ler(chave: str) -> dict | list:
    padrao = [] if chave in ("amistosos", "treinos", "partidas_campeonato", "emprestimos") else {}
    return ler_json(FILES[chave], padrao)


def salvar(chave: str, dados):
    salvar_json(FILES[chave], dados)


def agora_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        for chave in FILES:
            if not os.path.exists(FILES[chave]):
                salvar(chave, ler(chave))
        self.backup_loop.start()

    def cog_unload(self):
        self.backup_loop.cancel()

    @tasks.loop(hours=6)
    async def backup_loop(self):
        await self.bot.wait_until_ready()


        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            backup_dir = f"data/backups/{timestamp}"
            os.makedirs(backup_dir, exist_ok=True)

            for chave, path in FILES.items():
                if os.path.exists(path):
                    dados = ler(chave)
                    backup_path = f"{backup_dir}/{chave}.json"
                    salvar_json(backup_path, dados)


            backups = sorted(
                nome for nome in os.listdir("data/backups")
                if os.path.isdir(os.path.join("data/backups", nome))
            )
            while len(backups) > 10:
                antigo = backups.pop(0)
                try:
                    shutil.rmtree(os.path.join("data/backups", antigo))
                except OSError as e:
                    print(f"[BACKUP] ⚠️ Não foi possível remover backup antigo '{antigo}': {e}")

            print(f"[BACKUP] ✅ Backup realizado em {backup_dir}")
        except Exception as e:
            print(f"[BACKUP] ❌ Falha ao realizar backup automático: {e}")

    @backup_loop.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
