"""
Módulo: Utilitários do Sistema de Coaches
Arquivo: cogs/coach_utils.py
"""

from __future__ import annotations

import discord

from cogs.coach_config import MANAGER_ROLE_IDS, coach_por_chave

ESTRELAS_CHEIA = "⭐"
ESTRELAS_LABEL = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]


def eh_gerente(member: discord.Member) -> bool:
    """Staff/gerência: possui um dos cargos autorizados OU é administrador."""
    if member.guild_permissions.administrator:
        return True
    cargos_ids = {role.id for role in member.roles}
    return bool(cargos_ids & MANAGER_ROLE_IDS)


def eh_coach_responsavel(member: discord.Member, coach_key: str) -> bool:
    coach = coach_por_chave(coach_key)
    return bool(coach) and member.id == coach["user_id"]


def pode_finalizar(member: discord.Member, coach_key: str) -> bool:
    """Somente o coach responsável ou a staff/gerência."""
    return eh_coach_responsavel(member, coach_key) or eh_gerente(member)


def estrelas_texto(nota: int) -> str:
    if 1 <= nota <= 5:
        return ESTRELAS_LABEL[nota - 1]
    return ""


def barra_estatisticas(notas: dict) -> str:
    """Monta as linhas '★★★★★ 15' ... '★☆☆☆☆ 1' na ordem de 5 a 1 estrelas."""
    linhas = []
    for n in (5, 4, 3, 2, 1):
        cheias = "★" * n
        vazias = "☆" * (5 - n)
        qtd = notas.get(str(n), 0)
        linhas.append(f"{cheias}{vazias} {qtd}")
    return "\n".join(linhas)


def montar_embed_estatisticas(coach_nome: str, notas: dict) -> discord.Embed:
    total = sum(notas.get(str(n), 0) for n in range(1, 6))
    soma = sum(n * notas.get(str(n), 0) for n in range(1, 6))
    media = (soma / total) if total else 0.0

    embed = discord.Embed(
        title="📊 Estatísticas",
        description=f"**Coach {coach_nome}**\n\n{barra_estatisticas(notas)}",
        color=0x2B2D31,
    )
    embed.add_field(name="Total:", value=f"{total} avaliações", inline=True)
    embed.add_field(name="Média:", value=f"{media:.2f} ⭐", inline=True)
    return embed


def montar_embed_compra(coach_nome: str) -> discord.Embed:
    return discord.Embed(
        title="🛒 Comprar Atendimento",
        description=(
            f"Clique no botão abaixo para abrir um atendimento privado "
            f"com o coach **{coach_nome}**.\n\n"
            f"Um canal será criado apenas para você, o coach e a equipe staff."
        ),
        color=0x57F287,
    )


def montar_embed_ticket(coach_nome: str, cliente: discord.abc.User, status: str) -> discord.Embed:
    embed = discord.Embed(title="🎫 Atendimento com Coach", color=0x5865F2)
    embed.add_field(name="Coach", value=coach_nome, inline=True)
    embed.add_field(name="Cliente", value=cliente.mention, inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="\u200b",
        value="Quando finalizar o atendimento utilize `!finalizar-coach`",
        inline=False,
    )
    return embed


def montar_embed_avaliacao(cliente: discord.abc.User, nota: int, comentario: str) -> discord.Embed:
    embed = discord.Embed(
        title=estrelas_texto(nota),
        color=0xFEE75C,
    )
    embed.add_field(name="Cliente:", value=cliente.mention if hasattr(cliente, "mention") else str(cliente), inline=False)
    embed.add_field(name="Comentário:", value=comentario, inline=False)
    return embed
