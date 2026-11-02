"""Config do servidor de Minecraft (gravada pelo !setupmine em data/mc_config.json).
O .env serve de reserva. Tudo aqui é lido na hora do uso (o .env já está carregado)."""
import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "mc_config.json"

# Servidor de Minecraft. (Não confundir com GUILD_ID do .env, que é o servidor do Rocket.)
MC_GUILD_ID_PADRAO = 1566899003520716960


def _env_id(nome: str) -> int:
    valor = os.getenv(nome, "").strip()
    return int(valor) if valor.isdigit() else 0


def guild_id() -> int:
    return _env_id("MC_GUILD_ID") or MC_GUILD_ID_PADRAO


def carregar() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar(dados: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


def staff_role_ids() -> set[int]:
    ids = {int(i) for i in carregar().get("staff_role_ids", [])}
    if _env_id("MC_STAFF_ROLE_ID"):
        ids.add(_env_id("MC_STAFF_ROLE_ID"))
    return ids


def ping_role_id() -> int:
    return int(carregar().get("ping_role_id") or 0) or _env_id("MC_STAFF_ROLE_ID")


def member_role_id() -> int:
    return int(carregar().get("member_role_id") or 0) or _env_id("MC_MEMBER_ROLE_ID")


def no_access_role_id() -> int:
    """Cargo 'Sem Whitelist': dado a quem entra, removido ao ser aprovado."""
    return int(carregar().get("no_access_role_id") or 0) or _env_id("MC_NO_ACCESS_ROLE_ID")


def log_channel_id() -> int:
    return _env_id("MC_LOG_CHANNEL_ID")


def category_id() -> int:
    return _env_id("MC_CATEGORY_ID")
