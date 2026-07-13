"""
Módulo: Estatísticas e Ordenação de Mensagens do Sistema de Coaches
Arquivo: cogs/coach_stats.py

Regra fixa do canal de cada coach: as duas ÚLTIMAS mensagens do canal devem
SEMPRE ser, nessa ordem:

    1. 📊 Estatísticas das Avaliações
    2. 🛒 Comprar Atendimento

Como o Discord não permite "mover" uma mensagem existente para o fim do
canal, a única forma confiável de garantir a posição é apagar as duas
mensagens antigas (se existirem) e enviar duas novas. Por isso, toda vez que
alguma coisa for postada no canal (uma nova avaliação, ou qualquer mensagem
de terceiros), este módulo apaga e recria as duas mensagens fixas.
"""

from __future__ import annotations

import asyncio

import discord

from cogs.coach_config import coach_por_chave

# Um lock por coach — evita que duas reordenações do mesmo canal rodem ao
# mesmo tempo (ex: uma avaliação e uma mensagem de terceiro quase
# simultâneas) e acabem criando mensagens fixas duplicadas.
_locks_por_coach: dict[str, asyncio.Lock] = {}


def _lock_do_coach(coach_key: str) -> asyncio.Lock:
    if coach_key not in _locks_por_coach:
        _locks_por_coach[coach_key] = asyncio.Lock()
    return _locks_por_coach[coach_key]
from cogs.coach_storage import obter_coach_data, set_mensagens_coach
from cogs.coach_utils import montar_embed_estatisticas, montar_embed_compra
# Import feito dentro da função (e não aqui no topo) para evitar import
# circular: coach_views importa coach_manager, que importa coach_stats.


async def _apagar_mensagem_segura(channel: discord.TextChannel, mensagem_id: int | None) -> None:
    if not mensagem_id:
        return
    try:
        msg = await channel.fetch_message(mensagem_id)
        await msg.delete()
    except discord.NotFound:
        pass  # já tinha sido apagada — nada a fazer
    except discord.Forbidden:
        print(f"[COACH_STATS] ⚠️ Sem permissão para apagar mensagem {mensagem_id} em #{channel}.")
    except discord.HTTPException as e:
        print(f"[COACH_STATS] ⚠️ Erro ao apagar mensagem {mensagem_id} em #{channel}: {e}")


async def reordenar_mensagens_finais(bot: discord.Client, coach_key: str) -> None:
    """
    Apaga as mensagens antigas de Estatísticas/Comprar Atendimento (se
    existirem) e recria as duas, nessa ordem, garantindo que fiquem como as
    duas últimas mensagens do canal. Também é usada para "curar" o canal
    caso as mensagens tenham sido apagadas manualmente ou o bot tenha
    reiniciado.
    """
    coach = coach_por_chave(coach_key)
    if not coach:
        return

    channel = bot.get_channel(coach["channel_id"])
    if channel is None:
        try:
            channel = await bot.fetch_channel(coach["channel_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            print(f"[COACH_STATS] ⚠️ Canal do coach '{coach_key}' inacessível: {e}")
            return

    from cogs.coach_views import ComprarAtendimentoView  # import local — ver nota no topo do arquivo

    async with _lock_do_coach(coach_key):
        coach_data = await obter_coach_data(coach_key)

        # Apaga as antigas (segue a ordem pedida: estatísticas, depois comprar)
        await _apagar_mensagem_segura(channel, coach_data.get("stats_message_id"))
        await _apagar_mensagem_segura(channel, coach_data.get("buy_message_id"))

        # Recria — estatísticas primeiro, comprar atendimento por último (a
        # mais recente do canal)
        try:
            embed_stats = montar_embed_estatisticas(coach["nome"], coach_data.get("notas", {}))
            msg_stats = await channel.send(embed=embed_stats)

            embed_compra = montar_embed_compra(coach["nome"])
            msg_compra = await channel.send(embed=embed_compra, view=ComprarAtendimentoView(coach_key))

            await set_mensagens_coach(
                coach_key,
                stats_message_id=msg_stats.id,
                buy_message_id=msg_compra.id,
            )
        except discord.Forbidden:
            print(f"[COACH_STATS] ❌ Sem permissão para enviar mensagens no canal do coach '{coach_key}'.")
        except discord.HTTPException as e:
            print(f"[COACH_STATS] ❌ Erro ao recriar mensagens fixas do coach '{coach_key}': {e}")


async def garantir_mensagens_existem(bot: discord.Client, coach_key: str) -> None:
    """
    Usada no startup do bot: só recria as mensagens fixas se alguma delas
    estiver faltando (não existe ID salvo, ou a mensagem salva não existe
    mais). Se as duas já existem, não faz nada — evita apagar/recriar sem
    necessidade a cada restart.
    """
    coach = coach_por_chave(coach_key)
    if not coach:
        return

    channel = bot.get_channel(coach["channel_id"])
    if channel is None:
        try:
            channel = await bot.fetch_channel(coach["channel_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            print(f"[COACH_STATS] ⚠️ Canal do coach '{coach_key}' inacessível: {e}")
            return

    coach_data = await obter_coach_data(coach_key)
    precisa_recriar = False

    for msg_id in (coach_data.get("stats_message_id"), coach_data.get("buy_message_id")):
        if not msg_id:
            precisa_recriar = True
            break
        try:
            await channel.fetch_message(msg_id)
        except discord.NotFound:
            precisa_recriar = True
            break
        except (discord.Forbidden, discord.HTTPException):
            # Erro temporário/permissão — não força recriação por conta disso
            continue

    if precisa_recriar:
        await reordenar_mensagens_finais(bot, coach_key)
