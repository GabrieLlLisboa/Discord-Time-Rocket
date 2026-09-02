"""
Módulo: Persistência do Sistema de Coaches
Arquivo: cogs/coach_storage.py

Toda leitura/escrita passa por um único asyncio.Lock (_lock), garantindo que
sequências "ler -> modificar -> salvar" nunca sejam interrompidas por outra
tarefa concorrente (dois cliques simultâneos no mesmo botão, por exemplo).
A escrita em disco em si (salvar_json) já é atômica (arquivo temporário +
os.replace), reaproveitando o mesmo módulo usado pelo resto do bot
(cogs/json_store.py) — assim nunca fica um coaches.json "pela metade" caso
o processo seja encerrado no meio de uma gravação.

Nenhuma função aqui deve ser chamada diretamente para editar os dados "na
mão" — sempre usar as funções de alto nível (criar_ticket, finalizar_ticket,
marcar_avaliado, etc.), pois são elas que tomam o lock.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from cogs.json_store import ler_json, salvar_json

DATA_FILE = "data/coaches.json"

# Único lock do módulo — todas as operações de leitura+escrita passam por ele.
_lock = asyncio.Lock()


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _estrutura_padrao() -> dict:
    return {
        "tickets": {},      # str(canal_ticket_id) -> dados do ticket
        "coach_data": {},   # coach_key -> {stats_message_id, buy_message_id, notas}
    }


def _coach_data_padrao() -> dict:
    return {
        "stats_message_id": None,
        "buy_message_id": None,
        "notas": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
    }


def _ler() -> dict:
    dados = ler_json(DATA_FILE, _estrutura_padrao)
    # Garante as chaves-base mesmo se o arquivo já existia de uma versão antiga
    dados.setdefault("tickets", {})
    dados.setdefault("coach_data", {})
    return dados


def _salvar(dados: dict) -> None:
    salvar_json(DATA_FILE, dados)


def _garantir_coach_data(dados: dict, coach_key: str) -> dict:
    if coach_key not in dados["coach_data"]:
        dados["coach_data"][coach_key] = _coach_data_padrao()
    return dados["coach_data"][coach_key]


# ── Exceções específicas do domínio ─────────────────────────────────────────
class TicketJaAbertoError(Exception):
    """Já existe um ticket 'Em andamento' desse cliente com esse coach."""


class TicketNaoEncontradoError(Exception):
    pass


class TicketJaFinalizadoError(Exception):
    pass


class TicketJaAvaliadoError(Exception):
    pass


class TicketNaoFinalizadoError(Exception):
    """Tentativa de avaliar um ticket que ainda não foi finalizado."""


# ── Leitura simples (sem necessidade de lock — apenas consulta) ─────────────
async def obter_ticket(canal_ticket_id: int) -> Optional[dict]:
    async with _lock:
        return _ler()["tickets"].get(str(canal_ticket_id))


async def obter_coach_data(coach_key: str) -> dict:
    async with _lock:
        dados = _ler()
        return dict(_garantir_coach_data(dados, coach_key))


async def listar_tickets_para_reavaliacao() -> list[dict]:
    """Tickets finalizados mas ainda não avaliados — usados para recriar as
    Views persistentes do botão '⭐ Avaliar Coach' após um restart."""
    async with _lock:
        dados = _ler()
        return [
            t for t in dados["tickets"].values()
            if t.get("status") == "Concluído" and not t.get("avaliado")
        ]


async def listar_todos_tickets() -> list[dict]:
    async with _lock:
        return list(_ler()["tickets"].values())


# ── Operações atômicas de escrita ───────────────────────────────────────────
async def criar_ticket(cliente_id: int, coach_key: str, canal_ticket_id: int) -> dict:
    """
    Cria o registro do ticket de forma atômica. Levanta TicketJaAbertoError
    se o mesmo cliente já tiver um ticket 'Em andamento' com o mesmo coach —
    a verificação e a gravação acontecem sob o mesmo lock, então dois
    cliques simultâneos no botão "Comprar Atendimento" não conseguem
    resultar em dois tickets duplicados.
    """
    async with _lock:
        dados = _ler()

        for ticket in dados["tickets"].values():
            if (
                ticket["cliente_id"] == cliente_id
                and ticket["coach_key"] == coach_key
                and ticket["status"] == "Em andamento"
            ):
                raise TicketJaAbertoError()

        ticket = {
            "ticket_id": str(canal_ticket_id),
            "cliente_id": cliente_id,
            "coach_key": coach_key,
            "canal_ticket_id": canal_ticket_id,
            "canal_voz_id": None,
            "status": "Em andamento",
            "avaliado": False,
            "nota": None,
            "comentario": None,
            "criado_em": _agora(),
            "finalizado_em": None,
            "avaliado_em": None,
            "mensagem_avaliacao_publicada_id": None,
        }
        dados["tickets"][str(canal_ticket_id)] = ticket
        _salvar(dados)
        return dict(ticket)


async def finalizar_ticket(canal_ticket_id: int) -> dict:
    async with _lock:
        dados = _ler()
        chave = str(canal_ticket_id)
        ticket = dados["tickets"].get(chave)
        if ticket is None:
            raise TicketNaoEncontradoError()
        if ticket["status"] == "Concluído":
            raise TicketJaFinalizadoError()

        ticket["status"] = "Concluído"
        ticket["finalizado_em"] = _agora()
        _salvar(dados)
        return dict(ticket)


async def marcar_avaliado(canal_ticket_id: int, nota: int, comentario: str) -> dict:
    """
    Registra a avaliação e já atualiza o contador de estrelas do coach no
    mesmo lock/gravação — evita qualquer janela onde o ticket estivesse
    marcado como avaliado mas as estatísticas ainda não tivessem sido
    incrementadas (ou vice-versa).
    """
    async with _lock:
        dados = _ler()
        chave = str(canal_ticket_id)
        ticket = dados["tickets"].get(chave)
        if ticket is None:
            raise TicketNaoEncontradoError()
        if ticket["status"] != "Concluído":
            raise TicketNaoFinalizadoError()
        if ticket["avaliado"]:
            raise TicketJaAvaliadoError()

        ticket["avaliado"] = True
        ticket["nota"] = nota
        ticket["comentario"] = comentario
        ticket["avaliado_em"] = _agora()

        coach_data = _garantir_coach_data(dados, ticket["coach_key"])
        coach_data["notas"][str(nota)] = coach_data["notas"].get(str(nota), 0) + 1

        _salvar(dados)
        return dict(ticket)


async def registrar_mensagem_avaliacao(canal_ticket_id: int, mensagem_id: int) -> None:
    async with _lock:
        dados = _ler()
        ticket = dados["tickets"].get(str(canal_ticket_id))
        if ticket is not None:
            ticket["mensagem_avaliacao_publicada_id"] = mensagem_id
            _salvar(dados)


async def registrar_canal_voz(canal_ticket_id: int, canal_voz_id: int) -> None:
    async with _lock:
        dados = _ler()
        ticket = dados["tickets"].get(str(canal_ticket_id))
        if ticket is not None:
            ticket["canal_voz_id"] = canal_voz_id
            _salvar(dados)


async def set_mensagens_coach(
    coach_key: str,
    stats_message_id: Optional[int] = "__manter__",
    buy_message_id: Optional[int] = "__manter__",
) -> None:
    """Atualiza os IDs das mensagens fixas (estatísticas / comprar) do coach.
    Usar o sentinel "__manter__" (valor default) para não alterar aquele
    campo específico; passar None explicitamente para limpar o campo."""
    async with _lock:
        dados = _ler()
        coach_data = _garantir_coach_data(dados, coach_key)
        if stats_message_id != "__manter__":
            coach_data["stats_message_id"] = stats_message_id
        if buy_message_id != "__manter__":
            coach_data["buy_message_id"] = buy_message_id
        _salvar(dados)
