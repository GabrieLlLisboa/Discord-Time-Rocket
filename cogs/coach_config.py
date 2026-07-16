"""
Módulo: Configuração do Sistema de Coaches
Arquivo: cogs/coach_config.py

Único lugar que precisa ser editado para adicionar/remover um coach ou
alterar os cargos de gerenciamento. Nenhuma lógica dos demais módulos
(coach_storage, coach_manager, coach_views, coach_commands...) precisa
ser tocada ao adicionar um novo coach — basta um novo item no dicionário
COACHES abaixo.
"""

from __future__ import annotations

# ── Coaches ──────────────────────────────────────────────────────────────────
# chave interna -> { user_id do coach, channel_id do canal dele, nome de exibição }
COACHES: dict[str, dict] = {
    "isaque": {
        "user_id": 1421693641184772147,
        "channel_id": 1525158865426059274,
        "nome": "Isaque",
    },
    "whei": {
        "user_id": 1190705463310942208,
        "channel_id": 1525158888393932860,
        "nome": "Whei",
    },
    "borelli": {
        "user_id": 1454478828910022742,
        "channel_id": 1526771115538649128,
        "nome": "Borelli",
    },
}

# ── Cargos autorizados a gerenciar/finalizar tudo relacionado a coaches ──────
# (mesmos cargos usados para gerenciar/finalizar amistosos)
MANAGER_ROLE_IDS: set[int] = {
    1511895253777649704,
    1511894837790769204,
    1523843469016043600,
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
