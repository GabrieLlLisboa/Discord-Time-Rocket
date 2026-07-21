import discord
from discord.ext import commands
from discord import app_commands
from cogs.backup import ler, salvar, agora_str
import asyncio
import os
import re
import uuid

# ─────────────────────────────────────────────
#  Cog: Resultados
#  Arquivo: cogs/resultados.py
#  /resultado — registra resultado, salva transcrição,
#               DM nos jogadores e deleta canal
#  /ranking   — placar geral acumulado
# ─────────────────────────────────────────────

AMISTOSOS_CHANNEL_ID = 1514778555970621531

# Cargos autorizados a gerenciar/finalizar amistosos (mesmos cargos usados
# pelo sistema de coaches — ver cogs/coach_config.py).
ADMIN_ROLE_IDS = {
    1511895253777649704,
    1511894837790769204,
    1523843469016043600,
}

# Diretório dedicado (dentro de data/) pra transcrições temporárias.
TRANSCRICOES_DIR = "data/transcricoes"


def _nome_arquivo_seguro(adversario: str) -> str:
    """
    Constrói um nome de arquivo seguro a partir do texto livre digitado
    pelo usuário em `/resultado adversario:`.

    ANTES: o nome do arquivo era `f"transcricao-amistoso-{adversario...}.txt"`
    escrito direto no diretório de trabalho do bot, usando o texto do
    usuário quase sem filtrar (só trocava espaço por hífen). Como
    `adversario` é um campo de texto livre, alguém poderia digitar algo
    como "../../main" e o bot escreveria (e depois LERIA e reenviaria via
    DM/canal) um arquivo fora da pasta esperada — na prática, uma falha de
    path traversal / escrita arbitrária de arquivo. Mesmo sendo um comando
    restrito à staff, isso é perigoso (erro de digitação ou conta staff
    comprometida vira sobrescrita de arquivo do próprio bot).

    AGORA: qualquer caractere que não seja letra/número/hífen/underscore é
    removido, o nome fica limitado a 60 caracteres, e ainda é acrescentado
    um sufixo aleatório (uuid4) — isso também evita colisão entre dois
    amistosos contra adversários com nomes parecidos ou rodando ao mesmo
    tempo. O arquivo final sempre fica dentro de TRANSCRICOES_DIR.
    """
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", adversario.strip().lower()).strip("-")
    slug = slug[:60] or "adversario"
    nome = f"transcricao-amistoso-{slug}-{uuid.uuid4().hex[:8]}.txt"
    os.makedirs(TRANSCRICOES_DIR, exist_ok=True)
    return os.path.join(TRANSCRICOES_DIR, nome)


FRASES_JOGO = [
    "O jogo foi pegado!",
    "Foi um jogo difícil!",
    "Que partida intensa!",
    "O jogo foi disputado!",
]

FRASES_RESULTADO = {
    "vitoria": "Mas mesmo assim: **Ganhamos!** 🔥🏆",
    "derrota": "Mas mesmo assim: **Perdemos.** 💪 Cabeça erguida!",
    "empate":  "Mas mesmo assim: **Empatamos.** ⚖️",
}

TITULOS = {
    "vitoria": "✅ Vitória!",
    "derrota": "❌ Derrota!",
    "empate":  "🤝 Empate!",
}

import random


async def gerar_transcricao(canal: discord.TextChannel) -> str:
    """Gera uma transcrição simples em texto do canal."""
    linhas = [f"📄 Transcrição — #{canal.name}\n{'─'*40}\n"]
    async for msg in canal.history(limit=500, oldest_first=True):
        if msg.author.bot and not msg.embeds:
            continue
        hora = msg.created_at.strftime("%d/%m %H:%M")
        if msg.embeds:
            for e in msg.embeds:
                titulo = e.title or "Embed"
                linhas.append(f"[{hora}] 🤖 {msg.author.display_name}: [{titulo}]")
        else:
            linhas.append(f"[{hora}] {msg.author.display_name}: {msg.content}")
    return "\n".join(linhas)


class Resultados(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /resultado ────────────────────────────────────────────────────────────
    @app_commands.command(name="resultado", description="Registra o resultado de um amistoso.")
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
    @app_commands.describe(
        adversario="Nome do adversário",
        resultado="Resultado do amistoso",
        link_mensagem="Link da mensagem do anúncio do amistoso (clique com botão direito → Copiar Link)",
        descricao="Descrição livre sobre o jogo",
        placar="Placar final (ex: 3-1)",
    )
    @app_commands.choices(resultado=[
        app_commands.Choice(name="✅ Vitória", value="vitoria"),
        app_commands.Choice(name="❌ Derrota", value="derrota"),
        app_commands.Choice(name="🤝 Empate",  value="empate"),
    ])
    async def resultado(
        self,
        interaction: discord.Interaction,
        adversario: str,
        resultado: app_commands.Choice[str],
        link_mensagem: str,
        descricao: str = "",
        placar: str = "",
    ):
        await interaction.response.defer(ephemeral=True)

        amistosos  = ler("amistosos")
        resultados = ler("resultados")
        perfis     = ler("perfis")

        emoji_resultado = {"vitoria": "✅ Vitória", "derrota": "❌ Derrota", "empate": "🤝 Empate"}[resultado.value]
        cores           = {"vitoria": 0x57F287, "derrota": 0xED4245, "empate": 0xFEE75C}
        frase_jogo      = random.choice(FRASES_JOGO)
        frase_resultado = FRASES_RESULTADO[resultado.value]
        titulo_resultado = TITULOS[resultado.value]

        # Encontra o amistoso mais recente com esse adversário que AINDA NÃO
        # tenha um resultado registrado.
        #
        # ANTES: pegava o primeiro amistoso cujo nome batesse (substring) e
        # nunca checava se ele já tinha "resultado" preenchido. Isso permitia
        # rodar /resultado duas vezes pro mesmo amistoso (duplicando vitórias/
        # derrotas/partidas nos perfis, reenviando DMs e tentando deletar de
        # novo um canal que já tinha sido removido) e também escolher o
        # amistoso errado quando dois adversários tinham nomes parecidos.
        #
        # AGORA: ao encontrar um amistoso com "resultado" já preenchido
        # (inclusive cancelado), ele é ignorado e a busca continua por um
        # amistoso mais antigo, ainda em aberto, com o mesmo adversário. Se
        # só existirem amistosos já finalizados com esse nome, o comando é
        # bloqueado (nada é processado de novo) — isso torna a operação
        # idempotente: executar /resultado repetidas vezes para o mesmo
        # amistoso não tem mais efeito duplicado.
        amistoso_idx  = None
        canal_amistoso = None
        confirmados_ids = []
        amistoso_ja_processado = False

        for i in range(len(amistosos) - 1, -1, -1):
            if adversario.lower() in amistosos[i]["adversario"].lower():
                if amistosos[i].get("resultado"):
                    amistoso_ja_processado = True
                    continue
                amistoso_idx    = i
                confirmados_ids = amistosos[i].get("confirmados", [])
                canal_id        = amistosos[i].get("canal_id")
                if canal_id:
                    canal_amistoso = self.bot.get_channel(canal_id)
                break

        if amistoso_idx is None and amistoso_ja_processado:
            await interaction.followup.send(
                f"⚠️ Já existe um resultado registrado para o amistoso vs **{adversario}**. "
                f"Use `/listar_resultados` para conferir ou `/deletar_resultado` caso precise corrigir.",
                ephemeral=True
            )
            return

        # ── Gera transcrição antes de deletar o canal ──────────────────────
        transcricao_texto = None
        transcricao_arquivo = None

        if canal_amistoso:
            try:
                transcricao_texto   = await gerar_transcricao(canal_amistoso)
                nome_arquivo        = _nome_arquivo_seguro(adversario)
                transcricao_arquivo = nome_arquivo
                with open(nome_arquivo, "w", encoding="utf-8") as f:
                    f.write(transcricao_texto)
            except Exception as e:
                print(f"[RESULTADO] ⚠️ Erro ao gerar transcrição: {e}")

        # ── Atualiza histórico e perfis ────────────────────────────────────
        if amistoso_idx is not None:
            amistosos[amistoso_idx]["resultado"] = emoji_resultado
            amistosos[amistoso_idx]["placar"]    = placar
            salvar("amistosos", amistosos)

            for mid in confirmados_ids:
                sid = str(mid)
                if sid not in perfis:
                    perfis[sid] = {"nome": str(mid), "amistosos": 0, "vitorias": 0, "derrotas": 0}
                perfis[sid]["amistosos"] += 1
                if resultado.value == "vitoria":
                    perfis[sid]["vitorias"] += 1
                elif resultado.value == "derrota":
                    perfis[sid]["derrotas"] += 1
            salvar("perfis", perfis)

        resultados_lista = resultados if isinstance(resultados, list) else []
        resultados_lista.append({
            "adversario":     adversario,
            "resultado":      resultado.value,
            "placar":         placar,
            "data":           agora_str(),
            "registrado_por": interaction.user.display_name,
        })
        salvar("resultados", resultados_lista)

        # ── DM para cada jogador confirmado ────────────────────────────────
        placar_texto = f" — **{placar}**" if placar else ""
        dm_enviadas  = 0
        dm_falhas    = 0

        for mid in confirmados_ids:
            membro = interaction.guild.get_member(mid)
            if membro is None:
                continue
            try:
                # Monta a mensagem no formato pedido
                rank_amistoso = amistosos[amistoso_idx].get("rank", "") if amistoso_idx is not None else ""

                embed_dm = discord.Embed(
                    title=f"{titulo_resultado}  Ignition vs {adversario}",
                    color=cores[resultado.value],
                )
                embed_dm.add_field(name="🆚  Adversário", value=f"**{adversario}**", inline=True)
                if rank_amistoso:
                    embed_dm.add_field(name="🏅  Rank", value=f"**{rank_amistoso}**", inline=True)
                if placar:
                    embed_dm.add_field(name="🚗  Placar", value=f"**{placar}**", inline=True)

                linhas_dm = [frase_jogo, frase_resultado]
                if descricao:
                    linhas_dm.append(f"\n{descricao}")
                embed_dm.add_field(name="📝  Descrição", value="\n".join(linhas_dm), inline=False)
                embed_dm.add_field(name="📅  Data", value=agora_str(), inline=True)

                if transcricao_arquivo:
                    embed_dm.add_field(
                        name="📄  Transcrição do canal",
                        value="Se desejar ver a transcrição completa do canal do amistoso, ela está anexada abaixo.",
                        inline=False,
                    )

                embed_dm.set_footer(text="Ignition RL 🔥")

                dm = await membro.create_dm()
                if transcricao_arquivo:
                    await dm.send(
                        embed=embed_dm,
                        file=discord.File(transcricao_arquivo, filename=os.path.basename(transcricao_arquivo))
                    )
                else:
                    await dm.send(embed=embed_dm)

                dm_enviadas += 1
            except discord.Forbidden:
                dm_falhas += 1
                print(f"[RESULTADO] ⚠️ Não foi possível enviar DM para {membro}.")

        # ── Responde a mensagem do amistoso no canal ──────────────────────
        rank_amistoso = amistosos[amistoso_idx].get("rank", "") if amistoso_idx is not None else ""

        embed_pub = discord.Embed(
            title=titulo_resultado,
            color=cores[resultado.value],
        )
        embed_pub.add_field(name="🆚  Adversário", value=f"**{adversario}**", inline=True)
        if rank_amistoso:
            embed_pub.add_field(name="🏅  Rank", value=f"**{rank_amistoso}**", inline=True)
        if placar:
            embed_pub.add_field(name="🚗  Placar", value=f"**{placar}**", inline=True)

        linhas_pub = [frase_jogo, frase_resultado]
        if descricao:
            linhas_pub.append(f"\n{descricao}")
        embed_pub.add_field(name="📝  Descrição", value="\n".join(linhas_pub), inline=False)
        embed_pub.set_footer(text=f"Registrado por {interaction.user.display_name}")

        canal_pub = self.bot.get_channel(AMISTOSOS_CHANNEL_ID)
        if canal_pub:
            msg_amistoso = None
            # Extrai IDs do link: .../channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
            try:
                partes = link_mensagem.strip().split("/")
                msg_id = int(partes[-1])
                ch_id  = int(partes[-2])
                canal_link = self.bot.get_channel(ch_id)
                if canal_link:
                    msg_amistoso = await canal_link.fetch_message(msg_id)
            except Exception as e:
                print(f"[RESULTADO] ⚠️ Não foi possível buscar a mensagem pelo link: {e}")

            if msg_amistoso:
                await msg_amistoso.reply(embed=embed_pub)
            else:
                await canal_pub.send(embed=embed_pub)

        # ── Deleta o canal do amistoso ─────────────────────────────────────
        if canal_amistoso:
            await asyncio.sleep(3)
            try:
                await canal_amistoso.delete(reason=f"Amistoso vs {adversario} encerrado — resultado registrado.")
                print(f"[RESULTADO] 🗑️ Canal {canal_amistoso.name} deletado.")
            except Exception as e:
                print(f"[RESULTADO] ⚠️ Erro ao deletar canal: {e}")

        # Limpa arquivo de transcrição temporário
        if transcricao_arquivo:
            try:
                os.remove(transcricao_arquivo)
            except Exception:
                pass

        await interaction.followup.send(
            f"✅ Resultado registrado! {emoji_resultado} vs **{adversario}**{placar_texto}\n"
            f"📬 DMs enviadas: `{dm_enviadas}` | ❌ Falhas: `{dm_falhas}`",
            ephemeral=True
        )
        print(f"[RESULTADO] ✅ {resultado.value} vs {adversario} | DMs: {dm_enviadas}/{len(confirmados_ids)}")

    @resultado.error
    async def resultado_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem registrar resultados.", ephemeral=True
            )

    # ── /ranking ──────────────────────────────────────────────────────────────
    @app_commands.command(name="ranking", description="Placar acumulado de vitórias do time.")
    async def ranking(self, interaction: discord.Interaction):
        resultados = ler("resultados")
        if isinstance(resultados, dict):
            resultados = []

        total    = len(resultados)
        vitorias = sum(1 for r in resultados if r["resultado"] == "vitoria")
        derrotas = sum(1 for r in resultados if r["resultado"] == "derrota")
        empates  = sum(1 for r in resultados if r["resultado"] == "empate")
        winrate  = f"{round((vitorias / total) * 100)}%" if total > 0 else "—"

        embed = discord.Embed(title="🔥  Placar da Squad Ignition", color=0xFF5A1F)
        embed.add_field(name="\u200b", value="```╔══════════  📊  GERAL  ══════════╗```", inline=False)
        embed.add_field(name="🎮  Total",    value=f"`{total}`",    inline=True)
        embed.add_field(name="✅  Vitórias", value=f"`{vitorias}`", inline=True)
        embed.add_field(name="❌  Derrotas", value=f"`{derrotas}`", inline=True)
        embed.add_field(name="🤝  Empates",  value=f"`{empates}`",  inline=True)
        embed.add_field(name="📊  Winrate",  value=f"`{winrate}`",  inline=True)

        embed.set_footer(text=f"Ignition RL • {agora_str()}")

        if not resultados or len(resultados) <= 5:
            if resultados:
                embed.add_field(name="\u200b", value="```╔══════════  🕐  JOGOS  ══════════╗```", inline=False)
                for i, r in enumerate(resultados[::-1]):
                    num    = len(resultados) - 1 - i
                    emoji  = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}.get(r["resultado"], "❓")
                    placar = f" — {r['placar']}" if r.get("placar") else ""
                    embed.add_field(
                        name=f"`#{num}`  {emoji}  vs {r['adversario']}{placar}",
                        value=f"📅 {r['data']}",
                        inline=False,
                    )
            await interaction.response.send_message(embed=embed)
        else:
            from cogs.paginacao import paginar, PaginacaoView

            # Embed de resumo (sempre página 1)
            embed_resumo = embed

            def montar_pagina(pagina, total, fatia, offset):
                e = discord.Embed(title="🔥  Squad Ignition — Histórico de Jogos", color=0xFF5A1F)
                for i, r in enumerate(fatia):
                    num    = offset + i
                    emoji  = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}.get(r["resultado"], "❓")
                    placar = f" — {r['placar']}" if r.get("placar") else ""
                    e.add_field(
                        name=f"`#{num}`  {emoji}  vs {r['adversario']}{placar}",
                        value=f"📅 {r['data']}",
                        inline=False,
                    )
                e.set_footer(text=f"Página {pagina}/{total}  •  {len(resultados)} jogos no total")
                return e

            embeds = [embed_resumo] + paginar(resultados, 5, montar_pagina)
            view   = PaginacaoView(embeds)
            await interaction.response.send_message(embed=embeds[0], view=view)


    # ── /cancelar_amistoso ───────────────────────────────────────────────────
    @app_commands.command(name="cancelar_amistoso", description="Cancela um amistoso e notifica os jogadores.")
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
    @app_commands.describe(
        adversario="Nome do adversário (como foi anunciado)",
        link_mensagem="Link da mensagem do anúncio do amistoso",
        motivo="Motivo do cancelamento",
    )
    async def cancelar_amistoso(
        self,
        interaction: discord.Interaction,
        adversario: str,
        link_mensagem: str,
        motivo: str,
    ):
        await interaction.response.defer(ephemeral=True)

        amistosos = ler("amistosos")
        confirmados_ids = []
        canal_amistoso  = None
        amistoso_idx    = None

        for i in range(len(amistosos) - 1, -1, -1):
            if adversario.lower() in amistosos[i]["adversario"].lower():
                amistoso_idx    = i
                confirmados_ids = amistosos[i].get("confirmados", [])
                canal_id        = amistosos[i].get("canal_id")
                if canal_id:
                    canal_amistoso = self.bot.get_channel(canal_id)
                break

        # Atualiza histórico
        if amistoso_idx is not None:
            amistosos[amistoso_idx]["resultado"] = "❌ Cancelado"
            amistosos[amistoso_idx]["placar"]    = ""
            salvar("amistosos", amistosos)

        # Embed público respondendo ao anúncio
        embed_pub = discord.Embed(
            title="🚫  Amistoso Cancelado",
            color=0x808080,
        )
        embed_pub.add_field(name="🆚  Adversário", value=f"**{adversario}**", inline=True)
        embed_pub.add_field(name="📝  Motivo",     value=motivo,              inline=False)
        embed_pub.set_footer(text=f"Cancelado por {interaction.user.display_name}")
        embed_pub.timestamp = discord.utils.utcnow()

        canal_pub = self.bot.get_channel(AMISTOSOS_CHANNEL_ID)
        if canal_pub:
            msg_amistoso = None
            try:
                partes = link_mensagem.strip().split("/")
                msg_id    = int(partes[-1])
                ch_id     = int(partes[-2])
                canal_link = self.bot.get_channel(ch_id)
                if canal_link:
                    msg_amistoso = await canal_link.fetch_message(msg_id)
            except Exception as e:
                print(f"[CANCELAR] ⚠️ Não foi possível buscar a mensagem: {e}")

            if msg_amistoso:
                await msg_amistoso.reply(embed=embed_pub)
            else:
                await canal_pub.send(embed=embed_pub)

        # DM para cada jogador confirmado
        dm_enviadas = 0
        for mid in confirmados_ids:
            membro = interaction.guild.get_member(mid)
            if membro is None:
                continue
            try:
                embed_dm = discord.Embed(
                    title="🚫  Amistoso Cancelado",
                    description=f"O amistoso contra **{adversario}** foi cancelado.",
                    color=0x808080,
                )
                embed_dm.add_field(name="📝  Motivo", value=motivo, inline=False)
                embed_dm.set_footer(text="Ignition RL 🔥")
                dm = await membro.create_dm()
                await dm.send(embed=embed_dm)
                dm_enviadas += 1
            except discord.Forbidden:
                print(f"[CANCELAR] ⚠️ Não foi possível enviar DM para {membro}.")

        # Deleta o canal do amistoso
        if canal_amistoso:
            await asyncio.sleep(2)
            try:
                await canal_amistoso.delete(reason=f"Amistoso vs {adversario} cancelado.")
                print(f"[CANCELAR] 🗑️ Canal {canal_amistoso.name} deletado.")
            except Exception as e:
                print(f"[CANCELAR] ⚠️ Erro ao deletar canal: {e}")

        await interaction.followup.send(
            f"✅ Amistoso vs **{adversario}** cancelado. {dm_enviadas} jogador(es) notificados.",
            ephemeral=True
        )
        print(f"[CANCELAR] ✅ Amistoso vs {adversario} cancelado por {interaction.user} | DMs: {dm_enviadas}")

    @cancelar_amistoso.error
    async def cancelar_amistoso_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem cancelar amistosos.", ephemeral=True
            )


    # ── /listar_resultados ───────────────────────────────────────────────────
    @app_commands.command(name="listar_resultados", description="Lista todos os resultados com número para deletar.")
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
    async def listar_resultados(self, interaction: discord.Interaction):
        resultados = ler("resultados")
        if not isinstance(resultados, list) or not resultados:
            await interaction.response.send_message("📭 Nenhum resultado registrado.", ephemeral=True)
            return

        from cogs.paginacao import paginar, PaginacaoView

        def montar_embed(pagina, total, fatia, offset):
            embed = discord.Embed(title="📋  Resultados Registrados", color=0xFF5A1F)
            for i, r in enumerate(fatia):
                num    = offset + i
                emoji  = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}.get(r["resultado"], "❓")
                placar = f" — {r['placar']}" if r.get("placar") else ""
                embed.add_field(
                    name=f"`#{num}` {emoji} vs {r['adversario']}{placar}",
                    value=f"📅 {r['data']}",
                    inline=False,
                )
            embed.set_footer(text=f"Página {pagina}/{total}  •  Use /deletar_resultado com o número para remover.")
            return embed

        embeds = paginar(resultados, 5, montar_embed)
        view   = PaginacaoView(embeds, ephemeral=True) if len(embeds) > 1 else None
        await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)

    @listar_resultados.error
    async def listar_resultados_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("❌ Apenas **Administradores** podem usar este comando.", ephemeral=True)

    # ── /deletar_resultado ────────────────────────────────────────────────────
    @app_commands.command(name="deletar_resultado", description="Deleta um resultado pelo número (use /listar_resultados primeiro).")
    @app_commands.checks.has_any_role(*ADMIN_ROLE_IDS)
    @app_commands.describe(numero="Número do resultado (veja com /listar_resultados)")
    async def deletar_resultado(self, interaction: discord.Interaction, numero: int):
        resultados = ler("resultados")
        if not isinstance(resultados, list):
            await interaction.response.send_message("📭 Nenhum resultado registrado.", ephemeral=True)
            return

        if numero < 0 or numero >= len(resultados):
            await interaction.response.send_message(
                f"❌ Número inválido. Use um número entre `0` e `{len(resultados) - 1}`.",
                ephemeral=True
            )
            return

        removido = resultados.pop(numero)
        salvar("resultados", resultados)

        emoji = {"vitoria": "✅", "derrota": "❌", "empate": "🤝"}.get(removido["resultado"], "❓")
        placar = f" — {removido['placar']}" if removido.get("placar") else ""

        await interaction.response.send_message(
            f"🗑️ Resultado removido: `#{numero}` {emoji} vs **{removido['adversario']}**{placar}",
            ephemeral=True
        )
        print(f"[RESULTADO] 🗑️ #{numero} deletado por {interaction.user}: {removido}")

    @deletar_resultado.error
    async def deletar_resultado_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("❌ Apenas **Administradores** podem usar este comando.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Resultados(bot))
