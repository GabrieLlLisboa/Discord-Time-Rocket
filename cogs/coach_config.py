"""
Módulo: Configuração do Sistema de Coaches
Arquivo: cogs/coach_config.py

Os coaches "de fábrica" ficam fixos no dicionário COACHES abaixo. Coaches
adicionados depois, via `/adicionar-coach`, são gravados em
data/coaches_extra.json e recarregados automaticamente aqui sempre que o
bot reinicia — não precisa editar este arquivo à mão pra isso.
"""

from __future__ import annotations

import re

from cogs.json_store import ler_json, salvar_json

EXTRA_COACHES_FILE = "data/coaches_extra.json"

# ── Coaches ──────────────────────────────────────────────────────────────────
# chave interna -> { user_id do coach, channel_id do canal dele, nome de exibição }
COACHES: dict[str, dict] = {
    # Coaches de fábrica removidos (eram do servidor antigo).
    # Adicione novos coaches com o comando /adicionar-coach — eles ficam
    # salvos em data/coaches_extra.json e recarregados automaticamente aqui.
}

# Carrega os coaches adicionados via /adicionar-coach (persistidos em disco)
# e junta com os de fábrica acima.
COACHES.update(ler_json(EXTRA_COACHES_FILE, dict))

# ── Cargos autorizados a gerenciar/finalizar tudo relacionado a coaches ──────
# (mesmos cargos usados para gerenciar/finalizar amistosos)
MANAGER_ROLE_IDS: set[int] = {
    1511895253777649704,
    1529150684296122438,
    1529241192183627947,
}

# Categoria onde o canal de voz de cada atendimento é criado.
CATEGORIA_VOZ_ID: int = 1525158787894218884


def coach_por_chave(chave: str) -> dict | None:
    return COACHES.get(chave)


def coach_por_channel_id(channel_id: int) -> tuple[str, dict] | None:
    """Encontra o coach (chave, dados) dono do canal informado."""
    for chave, dados in COACHES.items():
        if dados["channel_id"] == channel_id:
            return chave, dados
    return None


def coach_por_user_id(user_id: int) -> tuple[str, dict] | None:
    """Encontra o coach (chave, dados) cujo user_id é o informado."""
    for chave, dados in COACHES.items():
        if dados["user_id"] == user_id:
            return chave, dados
    return None


def _gerar_chave(nome: str) -> str:
    """Transforma o nome de exibição numa chave interna simples (sem
    acentos/espaços), ex: 'Borelli 2' -> 'borelli_2'."""
    chave = nome.strip().lower()
    chave = re.sub(r"\s+", "_", chave)
    chave = re.sub(r"[^a-z0-9_]", "", chave)
    return chave or "coach"


class CoachJaExisteError(Exception):
    """Já existe um coach com essa chave, user_id ou channel_id."""


def adicionar_coach(user_id: int, channel_id: int, nome: str) -> str:
    """
    Adiciona um novo coach: gera a chave a partir do nome, valida que não
    haja conflito (mesma chave, mesmo usuário ou mesmo canal já
    cadastrados), atualiza o dicionário COACHES em memória e persiste em
    data/coaches_extra.json — assim o coach sobrevive a um restart do bot
    sem precisar editar este arquivo na mão. Devolve a chave gerada.
    """
    chave = _gerar_chave(nome)

    if chave in COACHES:
        raise CoachJaExisteError(f"já existe um coach com a chave '{chave}' (nome parecido demais).")
    if coach_por_user_id(user_id) is not None:
        raise CoachJaExisteError("esse usuário já é coach.")
    if coach_por_channel_id(channel_id) is not None:
        raise CoachJaExisteError("esse canal já está associado a outro coach.")

    dados = {"user_id": user_id, "channel_id": channel_id, "nome": nome}
    COACHES[chave] = dados

    extras = ler_json(EXTRA_COACHES_FILE, dict)
    extras[chave] = dados
    salvar_json(EXTRA_COACHES_FILE, extras)

    return chave
