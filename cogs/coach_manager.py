"""
Módulo: Orquestração do Sistema de Coaches
Arquivo: cogs/coach_manager.py

Camada "de negócio": conecta storage (coach_storage), views/embeds
(coach_views/coach_utils) e o Discord em si. As Views/Modals chamam estas
funções em vez de conter a lógica diretamente — mantém cada módulo com
responsabilidade única e evita duplicar regras em mais de um lugar.
"""

from __future__ import annotations

import asyncio

import discord

from cogs.coach_config import coach_por_chave, MANAGER_ROLE_IDS, CATEGORIA_VOZ_ID
from cogs.coach_storage import (
    criar_ticket,
    finalizar_ticket,
    marcar_avaliado,
    registrar_mensagem_avaliacao,
    registrar_canal_voz,
    TicketJaAbertoError,
    TicketNaoEncontradoError,
    TicketJaFinalizadoError,
    TicketJaAvaliadoError,
    TicketNaoFinalizadoError,
)
from cogs.coach_utils import montar_embed_ticket, montar_embed_avaliacao


# ── Criação do ticket (botão "🛒 Comprar Atendimento") ──────────────────────
async def criar_ticket_atendimento(interaction: discord.Interaction, coach_key: str) -> None:
    guild = interaction.guild
    cliente = interaction.user
    coach = coach_por_chave(coach_key)

    if guild is None or coach is None:
        await interaction.response.send_message(
            "❌ Não foi possível identificar o coach deste canal.", ephemeral=True
        )
        return

    coach_membro = guild.get_member(coach["user_id"])

    # ── Permissões do canal de ticket ────────────────────────────────────
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        cliente: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if coach_membro is not None:
        overwrites[coach_membro] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    for role_id in MANAGER_ROLE_IDS:
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    nome_canal = f"coach-{coach_key}-{cliente.id}"

    # Responde a interação logo — a criação de canal pode levar um instante
    # e o Discord exige resposta em até 3s.
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        canal_ticket = await guild.create_text_channel(
            name=nome_canal,
            overwrites=overwrites,
            reason=f"Atendimento de coach ({coach_key}) aberto por {cliente}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ O bot não tem permissão para criar o canal de atendimento.", ephemeral=True
        )
        return
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Erro ao criar o canal de atendimento: {e}", ephemeral=True)
        return

    try:
        await criar_ticket(cliente.id, coach_key, canal_ticket.id)
    except TicketJaAbertoError:
        # Já existe um atendimento em andamento — desfaz o canal criado
        # (evita canal "órfão" sem registro correspondente) e avisa.
        try:
            await canal_ticket.delete(reason="Ticket duplicado — cliente já possui atendimento em andamento.")
        except discord.HTTPException:
            pass
        await interaction.followup.send(
            "⚠️ Você já possui um atendimento em andamento com este coach.", ephemeral=True
        )
        return

    # ── Canal de voz privado (só cliente + coach) ────────────────────────
    canal_voz = None
    categoria_voz = guild.get_channel(CATEGORIA_VOZ_ID)
    if categoria_voz is not None:
        overwrites_voz = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, connect=True),
            cliente: discord.PermissionOverwrite(view_channel=True, connect=True),
        }
        if coach_membro is not None:
            overwrites_voz[coach_membro] = discord.PermissionOverwrite(view_channel=True, connect=True)

        try:
            canal_voz = await guild.create_voice_channel(
                name=f"🔊-{coach_key}-{cliente.display_name}"[:100],
                category=categoria_voz,
                overwrites=overwrites_voz,
                reason=f"Canal de voz de atendimento ({coach_key}) para {cliente}",
            )
            await registrar_canal_voz(canal_ticket.id, canal_voz.id)
        except discord.Forbidden:
            print(f"[COACH] ⚠️ Sem permissão para criar canal de voz do ticket {canal_ticket.id}.")
        except discord.HTTPException as e:
            print(f"[COACH] ⚠️ Erro ao criar canal de voz do ticket {canal_ticket.id}: {e}")
    else:
        print(f"[COACH] ⚠️ Categoria de voz ({CATEGORIA_VOZ_ID}) não encontrada — canal de voz não criado.")

    embed = montar_embed_ticket(coach["nome"], cliente, "Em andamento")
    conteudo = f"{cliente.mention} " + (coach_membro.mention if coach_membro else "")
    if canal_voz is not None:
        conteudo += f"\n🔊 Canal de voz do atendimento: {canal_voz.mention}"
    try:
        await canal_ticket.send(content=conteudo, embed=embed)
    except discord.HTTPException as e:
        print(f"[COACH] ⚠️ Erro ao enviar mensagem inicial do ticket {canal_ticket.id}: {e}")

    await interaction.followup.send(
        f"✅ Atendimento criado: {canal_ticket.mention}", ephemeral=True
    )
    print(f"[COACH] ✅ Ticket {nome_canal} criado para {cliente} (coach: {coach_key}).")


# ── Finalização (comando !finalizar-coach) ──────────────────────────────────
async def finalizar_atendimento(channel: discord.TextChannel) -> dict:
    """
    Marca o ticket do canal informado como Concluído e envia o aviso ao
    cliente com o botão de avaliação. Levanta as exceções de
    coach_storage (TicketNaoEncontradoError / TicketJaFinalizadoError) que
    devem ser tratadas por quem chama (o comando, que já validou
    permissão antes de chegar aqui).
    """
    from cogs.coach_storage import obter_ticket
    from cogs.coach_views import AvaliarCoachView

    ticket_antes = await obter_ticket(channel.id)
    if ticket_antes is None:
        raise TicketNaoEncontradoError()

    ticket = await finalizar_ticket(channel.id)  # levanta TicketJaFinalizadoError se preciso

    canal_voz_id = ticket.get("canal_voz_id")
    if canal_voz_id:
        canal_voz = channel.guild.get_channel(canal_voz_id)
        if canal_voz is not None:
            try:
                await canal_voz.delete(reason=f"Atendimento finalizado — ticket {channel.id}")
            except discord.HTTPException as e:
                print(f"[COACH] ⚠️ Erro ao apagar canal de voz do ticket {channel.id}: {e}")

    cliente = channel.guild.get_member(ticket["cliente_id"])
    mencao_cliente = cliente.mention if cliente else f"<@{ticket['cliente_id']}>"

    try:
        await channel.send(
            f"{mencao_cliente}\n\n"
            f"Seu atendimento foi finalizado!\n"
            f"Clique abaixo para avaliar o coach.",
            view=AvaliarCoachView(channel.id),
        )
    except discord.HTTPException as e:
        print(f"[COACH] ⚠️ Erro ao enviar aviso de finalização no ticket {channel.id}: {e}")

    return ticket


# ── Avaliação (Modal de comentário) ──────────────────────────────────────────
async def concluir_avaliacao(
    interaction: discord.Interaction,
    canal_ticket_id: int,
    nota: int,
    comentario: str,
) -> None:
    from cogs.coach_stats import reordenar_mensagens_finais

    try:
        ticket = await marcar_avaliado(canal_ticket_id, nota, comentario)
    except TicketNaoEncontradoError:
        await interaction.response.send_message(
            "❌ Este atendimento não foi encontrado.", ephemeral=True
        )
        return
    except TicketNaoFinalizadoError:
        await interaction.response.send_message(
            "❌ Este atendimento ainda não foi finalizado.", ephemeral=True
        )
        return
    except TicketJaAvaliadoError:
        await interaction.response.send_message(
            "⚠️ Você já avaliou este atendimento.", ephemeral=True
        )
        return

    coach = coach_por_chave(ticket["coach_key"])
    if coach is None:
        await interaction.response.send_message(
            "✅ Avaliação registrada, mas o coach não foi encontrado para publicação.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message("✅ Avaliação registrada, obrigado!", ephemeral=True)

    canal_coach = interaction.client.get_channel(coach["channel_id"])
    if canal_coach is None:
        try:
            canal_coach = await interaction.client.fetch_channel(coach["channel_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            print(f"[COACH] ⚠️ Não foi possível acessar o canal do coach '{ticket['coach_key']}': {e}")
            return

    # 1. Publica a avaliação
    try:
        embed = montar_embed_avaliacao(interaction.user, nota, comentario)
        msg = await canal_coach.send(embed=embed)
        await registrar_mensagem_avaliacao(canal_ticket_id, msg.id)
    except discord.HTTPException as e:
        print(f"[COACH] ⚠️ Erro ao publicar avaliação do ticket {canal_ticket_id}: {e}")

    # 2-5. Atualiza estatísticas e recria as duas mensagens fixas no final do canal
    await reordenar_mensagens_finais(interaction.client, ticket["coach_key"])

    # 6. Apaga o canal do atendimento — o cliente já avaliou, não precisa mais dele
    canal_ticket = interaction.client.get_channel(canal_ticket_id)
    if canal_ticket is None:
        try:
            canal_ticket = await interaction.client.fetch_channel(canal_ticket_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            canal_ticket = None

    if canal_ticket is not None:
        try:
            await canal_ticket.send("✅ Avaliação recebida — este canal será apagado em alguns segundos.")
        except discord.HTTPException:
            pass
        await asyncio.sleep(5)
        try:
            await canal_ticket.delete(reason=f"Atendimento avaliado pelo cliente — ticket {canal_ticket_id}")
        except discord.HTTPException as e:
            print(f"[COACH] ⚠️ Erro ao apagar o canal do ticket {canal_ticket_id}: {e}")
