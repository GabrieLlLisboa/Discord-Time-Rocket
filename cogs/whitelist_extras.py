"""
Módulo: Extras da Whitelist
Arquivo: cogs/whitelist_extras.py

Duas coisas que a whitelist precisa guardar POR FORA do registro de cada
membro (porque o registro é recriado quando a pessoa sai e entra de novo):

1) Estatísticas da staff — quantas whitelists cada pessoa já aprovou/recusou
   (data/whitelist_stats.json). Aparece no /perfil de quem tem o cargo da
   whitelist.

2) Histórico de expulsões/banimentos (data/whitelist_historico.json) — usado
   pra avisar a staff, ANTES de aprovar, que a pessoa já foi expulsa/banida.
   Junta três fontes: o que o bot registrou sozinho (eventos de ban/kick e
   whitelists recusadas), o registro de punições da moderação
   (data/mod_punicoes.json) e o Audit Log do Discord (que só guarda ~45 dias).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import discord

from cogs.json_store import ler_json, salvar_json

# Cargo com acesso total às whitelists (aprovar, recusar, ver canais...).
CARGO_STAFF_WHITELIST_ID = 1555247132053864521

STATS_PATH = "data/whitelist_stats.json"
HIST_PATH = "data/whitelist_historico.json"

# duas punições do mesmo tipo dentro dessa janela contam como a MESMA
# (o evento do Discord, o audit log e o registro do bot descrevem o mesmo kick)
JANELA_DUPLICADA_SEGUNDOS = 300
MAX_LINHAS_AVISO = 5

TIPOS_PUNICAO_RELEVANTES = {"kick", "ban", "tempban", "softban"}

ROTULOS = {
    "kick":    ("👢", "Expulsão"),
    "ban":     ("🔨", "Banimento"),
    "tempban": ("⏳🔨", "Banimento temporário"),
    "softban": ("🧹🔨", "Softban"),
}


# ── estatísticas da staff ──────────────────────────────────────────────────
def obter_stats(user_id: int) -> tuple[int, int]:
    """Devolve (aprovadas, recusadas) de um membro da staff."""
    dados = ler_json(STATS_PATH, dict)
    reg = dados.get(str(user_id), {})
    return int(reg.get("aprovadas", 0)), int(reg.get("recusadas", 0))


def registrar_decisao(user_id: int, status: str) -> None:
    """Soma +1 em aprovadas/recusadas de quem tomou a decisão."""
    if status not in ("aprovada", "recusada"):
        return
    campo = "aprovadas" if status == "aprovada" else "recusadas"
    dados = ler_json(STATS_PATH, dict)
    reg = dados.setdefault(str(user_id), {"aprovadas": 0, "recusadas": 0})
    reg[campo] = int(reg.get(campo, 0)) + 1
    salvar_json(STATS_PATH, dados)


def preencher_stats_se_vazio(registros_whitelist: dict) -> None:
    """Na primeira vez (arquivo ainda não existe) conta as whitelists que já
    estão no data/whitelist.json, pra staff não começar do zero."""
    import os
    if os.path.exists(STATS_PATH):
        return
    dados: dict = {}
    for registro in registros_whitelist.values():
        status = registro.get("status")
        quem = registro.get("decidido_por_id")
        if status not in ("aprovada", "recusada") or not quem:
            continue
        reg = dados.setdefault(str(quem), {"aprovadas": 0, "recusadas": 0})
        reg["aprovadas" if status == "aprovada" else "recusadas"] += 1
    salvar_json(STATS_PATH, dados)


# ── histórico de expulsões / banimentos ────────────────────────────────────
def registrar_punicao_historico(user_id: int, tipo: str, motivo: str | None,
                                por_id: int | None = None, ts: float | None = None) -> bool:
    """Guarda uma expulsão/banimento. Devolve False se já existia uma igual
    (mesmo tipo dentro da janela de duplicadas)."""
    ts = ts or time.time()
    dados = ler_json(HIST_PATH, dict)
    lista = dados.setdefault(str(user_id), [])
    for e in lista:
        if e.get("tipo") == tipo and abs(e.get("ts", 0) - ts) <= JANELA_DUPLICADA_SEGUNDOS:
            # se a duplicada veio sem motivo e agora temos um, completa
            if motivo and not e.get("motivo"):
                e["motivo"] = motivo
                if por_id and not e.get("por_id"):
                    e["por_id"] = por_id
                salvar_json(HIST_PATH, dados)
            return False
    lista.append({"tipo": tipo, "motivo": motivo or "", "por_id": por_id, "ts": ts})
    salvar_json(HIST_PATH, dados)
    return True


def _entradas_locais(user_id: int) -> list[dict]:
    return list(ler_json(HIST_PATH, dict).get(str(user_id), []))


def _entradas_moderacao(guild_id: int, user_id: int) -> list[dict]:
    from cogs import mod_utils as mu
    saida = []
    try:
        for r in mu.historico_usuario(guild_id, user_id):
            if r.get("tipo") not in TIPOS_PUNICAO_RELEVANTES:
                continue
            try:
                ts = datetime.fromisoformat(r["criado_em"]).timestamp()
            except (KeyError, ValueError):
                continue
            saida.append({
                "tipo": r["tipo"], "motivo": r.get("motivo") or "",
                "por_id": r.get("moderador_id"), "ts": ts,
            })
    except Exception as e:  # arquivo de moderação ausente/corrompido não pode travar a aprovação
        print(f"[WHITELIST] ⚠️ Não consegui ler o histórico de moderação: {e}")
    return saida


async def _entradas_audit_log(guild: discord.Guild, user_id: int) -> list[dict]:
    """Procura expulsões/banimentos desse usuário no Audit Log (guarda ~45 dias)."""
    saida = []
    for acao, tipo in ((discord.AuditLogAction.kick, "kick"), (discord.AuditLogAction.ban, "ban")):
        try:
            async for entry in guild.audit_logs(limit=100, action=acao):
                if getattr(entry.target, "id", None) != user_id:
                    continue
                saida.append({
                    "tipo": tipo, "motivo": entry.reason or "",
                    "por_id": entry.user.id if entry.user else None,
                    "ts": entry.created_at.timestamp(),
                })
        except (discord.Forbidden, discord.HTTPException):
            # sem permissão de Ver Registro de Auditoria: segue só com as outras fontes
            continue
    return saida


def _unir(entradas: list[dict]) -> list[dict]:
    """Junta as fontes tirando duplicadas (mesmo tipo na mesma janela de tempo),
    preferindo a versão que tem motivo. Mais recentes primeiro."""
    unicas: list[dict] = []
    for e in sorted(entradas, key=lambda x: x.get("ts", 0)):
        igual = next((u for u in unicas
                      if u["tipo"] == e["tipo"] and abs(u["ts"] - e["ts"]) <= JANELA_DUPLICADA_SEGUNDOS), None)
        if igual is None:
            unicas.append(dict(e))
        else:
            if not igual.get("motivo") and e.get("motivo"):
                igual["motivo"] = e["motivo"]
            if not igual.get("por_id") and e.get("por_id"):
                igual["por_id"] = e["por_id"]
    return sorted(unicas, key=lambda x: x["ts"], reverse=True)


async def buscar_historico(guild: discord.Guild, user_id: int) -> list[dict]:
    entradas = _entradas_locais(user_id) + _entradas_moderacao(guild.id, user_id)
    entradas += await _entradas_audit_log(guild, user_id)
    return _unir(entradas)


def texto_aviso_historico(mencao: str, historico: list[dict]) -> str:
    """Mensagem de confirmação mostrada à staff antes de aceitar de volta."""
    foi_banido = any(e["tipo"] in ("ban", "tempban", "softban") for e in historico)
    foi_expulso = any(e["tipo"] == "kick" for e in historico)
    if foi_banido and foi_expulso:
        o_que = "expulso(a) e banido(a)"
    elif foi_banido:
        o_que = "banido(a)"
    else:
        o_que = "expulso(a)"

    linhas = []
    for e in historico[:MAX_LINHAS_AVISO]:
        emoji, nome = ROTULOS.get(e["tipo"], ("⚠️", e["tipo"]))
        quando = f"<t:{int(e['ts'])}:D>"
        por = f" por <@{e['por_id']}>" if e.get("por_id") else ""
        motivo = (e.get("motivo") or "").strip() or "motivo não informado"
        if len(motivo) > 160:
            motivo = motivo[:157] + "..."
        linhas.append(f"{emoji} **{nome}** em {quando}{por} — motivo: **{motivo}**")
    if len(historico) > MAX_LINHAS_AVISO:
        linhas.append(f"*(+{len(historico) - MAX_LINHAS_AVISO} registro(s) mais antigo(s))*")

    return (
        f"⚠️ **Atenção!** {mencao} já foi **{o_que}** deste servidor antes:\n\n"
        + "\n".join(linhas)
        + "\n\n**Tem certeza que deseja aceitá-lo(a) de volta?** Recomendo verificar antes."
    )
