from discord.ext import commands, tasks
import os
import shutil
from datetime import datetime, timezone

from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Backup Automático
#  Arquivo: cogs/backup.py
#  Salva dados a cada 6 horas em /data/
# ─────────────────────────────────────────────

DATA_DIR = "data"

# Arquivos de dados
FILES = {
    "amistosos":    "data/amistosos.json",
    "resultados":   "data/resultados.json",
    "perfis":       "data/perfis.json",
    "treinos":      "data/treinos.json",
    "demotados":    "data/demotados.json",
    "whitelist":    "data/whitelist.json",
    "enquetes":     "data/enquetes.json",
    # ANTES: campeonatos.json era usado normalmente pelo cog de campeonatos
    # (cogs/campeonato.py) mas não fazia parte desta lista — ou seja, não
    # entrava na rotina automática de backup nem era restaurado junto com os
    # demais arquivos em caso de corrupção. AGORA ele participa do mesmo
    # ciclo de backup/restauração que todos os outros arquivos de dados.
    "campeonatos":  "data/campeonatos.json",
}

os.makedirs(DATA_DIR, exist_ok=True)


# ── Helpers de leitura/escrita ─────────────────────────────────────────────────
# NOTA: a leitura/escrita real (com escrita atômica + proteção contra JSON
# corrompido) mora em cogs/json_store.py e é compartilhada com os outros
# cogs que também guardam dados em JSON (evita ter a mesma lógica de I/O
# duplicada, cada cópia com um nível de segurança diferente).
def ler(chave: str) -> dict | list:
    padrao = [] if chave in ("amistosos", "treinos") else {}
    return ler_json(FILES[chave], padrao)


def salvar(chave: str, dados):
    salvar_json(FILES[chave], dados)


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
        # Por padrão, se uma exceção não tratada acontecer dentro de um
        # @tasks.loop, o discord.py registra o erro e PARA o loop de vez
        # (não tenta de novo em 6h). Isso significa que uma falha pontual
        # (ex: disco cheio por um instante) faria os backups automáticos
        # pararem silenciosamente pro resto da vida do processo. O
        # try/except abaixo garante que só aquele ciclo falha — o próximo
        # ainda roda normalmente em 6h.
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            backup_dir = f"data/backups/{timestamp}"
            os.makedirs(backup_dir, exist_ok=True)

            for chave, path in FILES.items():
                if os.path.exists(path):
                    dados = ler(chave)
                    backup_path = f"{backup_dir}/{chave}.json"
                    salvar_json(backup_path, dados)

            # Mantém apenas os últimos 10 backups
            # (só considera diretórios — um arquivo perdido em data/backups,
            # tipo um .DS_Store ou um .tmp deixado por uma escrita
            # interrompida, não deve derrubar o loop por exceção)
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
