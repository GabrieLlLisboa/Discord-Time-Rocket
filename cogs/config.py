"""Config gravada pelo !setupmine (data/config.json). O .env serve de reserva."""
import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "config.json"


def _env_id(nome: str) -> int:
    valor = os.getenv(nome, "").strip()
    return int(valor) if valor.isdigit() else 0


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
    if _env_id("STAFF_ROLE_ID"):
        ids.add(_env_id("STAFF_ROLE_ID"))
    return ids


def ping_role_id() -> int:
    return int(carregar().get("ping_role_id") or 0) or _env_id("STAFF_ROLE_ID")


def member_role_id() -> int:
    return int(carregar().get("member_role_id") or 0) or _env_id("MEMBER_ROLE_ID")
