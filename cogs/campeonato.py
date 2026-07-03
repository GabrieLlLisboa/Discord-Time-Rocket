import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timezone

from cogs.players import CARGOS

# ─────────────────────────────────────────────
#  Cog: Campeonatos / Torneios
#  Arquivo: cogs/campeonato.py
#
#  /criar-campeonato e /torneiar são slash commands.
#  !destornear continua sendo comando de prefixo (!).
#
#  Cada campeonato gera DUAS mensagens no canal:
#    1) A mensagem de informações + botão "Entrar no Torneio"
#    2) A mensagem com a lista de inscritos (atualizada à parte)
# ─────────────────────────────────────────────

DATA_FILE = "data/campeonatos.json"

RANKS_VALIDOS = {c["nome"].lower(): c for c in CARGOS if c["secao"] == "rank"}
RANK_TODOS = "Todos"

RANK_CHOICES = [app_commands.Choice(name=c["nome"], value=c["nome"]) for c in CARGOS if c["secao"] == "rank"]
RANK_CHOICES.append(app_commands.Choice(name="Todos os ranks", value=RANK_TODOS))

FORMATO_CHOICES = [
    app_commands.Choice(name="1v1", value="1v1"),
    app_commands.Choice(name="2v2", value="2v2"),
    app_commands.Choice(name="3v3", value="3v3"),
]

TIPO_CHOICES = [
    app_commands.Choice(name="Interno", value="Interno"),
    app_commands.Choice(name="Externo", value="Externo"),
]


def ler_campeonatos() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_campeonatos(dados: dict):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _chave(nome: str) -> str:
    return nome.strip().lower()


def _membro_tem_rank(membro: discord.Member, rank_nome: str) -> bool:
    if rank_nome == RANK_TODOS:
        return True
    info = RANKS_VALIDOS.get(rank_nome.lower())
    if info is None:
        return True  # rank desconhecido — não bloqueia, deixa passar
    return any(r.id == info["id"] for r in membro.roles)


def _rank_display(rank_nome: str) -> str:
    if rank_nome == RANK_TODOS:
        return "Todos os ranks"
    info = RANKS_VALIDOS.get(rank_nome.lower())
    return f"{info['emoji']} {info['nome']}" if info else rank_nome


def construir_embed_info(info: dict) -> discord.Embed:
    """Mensagem 1: informações do campeonato (não muda depois de criada)."""
    embed = discord.Embed(title=f"🏆 Campeonato: {info['nome']}", color=0xD4A843)
    embed.add_field(name="🎮 Rank exigido", value=_rank_display(info["rank"]), inline=True)
    embed.add_field(name="⚔️ Formato", value=info["formato"], inline=True)
    embed.add_field(name="🌍 Tipo", value=info["tipo"], inline=True)
    embed.add_field(name="🧑‍💼 Organizador", value=info["organizador"], inline=False)
    embed.set_footer(text="Clique no botão abaixo pra se inscrever!")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def construir_embed_lista(info: dict) -> discord.Embed:
    """Mensagem 2: lista de inscritos (atualizada toda vez que alguém entra/sai)."""
    inscritos = info.get("inscritos", {})
    embed = discord.Embed(
        title=f"📋 Lista de inscritos — {info['nome']}",
        description="\n".join(f"▸ <@{uid}>" for uid in inscritos.keys()) if inscritos else "*— ninguém inscrito ainda —*",
        color=0xD4A843,
    )
    embed.set_footer(text=f"{len(inscritos)} inscrito(s)")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


async def _atualizar_lista(bot: commands.Bot, chave: str):
    dados = ler_campeonatos()
    info = dados.get(chave)
    if info is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is None:
        return
    try:
        msg = await canal.fetch_message(info["lista_message_id"])
        await msg.edit(embed=construir_embed_lista(info))
    except discord.NotFound:
        pass


# ── Modal que pergunta o país da pessoa ──────────────────────────────────────
class PaisModal(discord.ui.Modal, title="Inscrição no Torneio"):
    pais = discord.ui.TextInput(label="Qual o seu país?", placeholder="Ex: Brasil", max_length=50)

    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__()
        self.chave = chave
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        dados = ler_campeonatos()
        info = dados.get(self.chave)
        if info is None:
            await interaction.response.send_message("❌ Esse campeonato não existe mais.", ephemeral=True)
            return
        if str(interaction.user.id) in info["inscritos"]:
            await interaction.response.send_message("⚠️ Você já está inscrito nesse campeonato.", ephemeral=True)
            return

        info["inscritos"][str(interaction.user.id)] = {"pais": str(self.pais)}
        salvar_campeonatos(dados)
        await _atualizar_lista(self.bot, self.chave)
        await interaction.response.send_message(
            f"✅ Inscrição confirmada no campeonato **{info['nome']}**!", ephemeral=True
        )


# ── View de confirmação quando o rank não bate ───────────────────────────────
class ConfirmarRankView(discord.ui.View):
    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__(timeout=60)
        self.chave = chave
        self.bot = bot

    @discord.ui.button(label="Sim, quero mesmo assim", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PaisModal(self.chave, self.bot))

    @discord.ui.button(label="Não, cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Inscrição cancelada.", view=None)


# ── View fixa no anúncio do campeonato (persistente, sobrevive a restart) ───
class EntrarTorneioView(discord.ui.View):
    def __init__(self, chave: str):
        super().__init__(timeout=None)
        self.chave = chave
        self.entrar.custom_id = f"campeonato_entrar:{chave}"

    @discord.ui.button(label="🎮 Entrar no Torneio", style=discord.ButtonStyle.primary)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        dados = ler_campeonatos()
        info = dados.get(self.chave)
        if info is None:
            await interaction.response.send_message("❌ Esse campeonato não existe mais.", ephemeral=True)
            return
        if str(interaction.user.id) in info["inscritos"]:
            await interaction.response.send_message("⚠️ Você já está inscrito nesse campeonato.", ephemeral=True)
            return

        membro = interaction.user
        if isinstance(membro, discord.Member) and _membro_tem_rank(membro, info["rank"]):
            await interaction.response.send_modal(PaisModal(self.chave, bot))
        else:
            await interaction.response.send_message(
                f"⚠️ Esse campeonato pede o rank **{info['rank']}**, e você não tem esse cargo. "
                f"Deseja se inscrever mesmo assim?",
                view=ConfirmarRankView(self.chave, bot),
                ephemeral=True,
            )


async def _apagar_campeonato(bot: commands.Bot, chave: str):
    dados = ler_campeonatos()
    info = dados.get(chave)
    if info is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is not None:
        for msg_id in (info.get("message_id"), info.get("lista_message_id")):
            if msg_id is None:
                continue
            try:
                msg = await canal.fetch_message(msg_id)
                await msg.delete()
            except discord.NotFound:
                pass
    del dados[chave]
    salvar_campeonatos(dados)


class ConfirmarExclusaoView(discord.ui.View):
    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__(timeout=30)
        self.chave = chave
        self.bot = bot

    @discord.ui.button(label="Sim, apagar", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _apagar_campeonato(self.bot, self.chave)
        await interaction.response.edit_message(content="🗑️ Campeonato apagado.", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelado, o campeonato continua ativo.", view=None)


async def _autocomplete_campeonato(interaction: discord.Interaction, current: str):
    dados = ler_campeonatos()
    return [
        app_commands.Choice(name=info["nome"], value=info["nome"])
        for info in dados.values()
        if current.lower() in info["nome"].lower()
    ][:25]


class Campeonato(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /criar-campeonato ────────────────────────────────────────────────────
    @app_commands.command(name="criar-campeonato", description="Cria o anúncio de um campeonato com botão de inscrição.")
    @app_commands.describe(
        nome="Nome do campeonato",
        rank="Rank exigido pra participar (ou 'Todos os ranks')",
        formato="Formato das partidas",
        tipo="O campeonato é interno ou externo?",
        organizador="Quem está organizando",
    )
    @app_commands.choices(rank=RANK_CHOICES, formato=FORMATO_CHOICES, tipo=TIPO_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def criar_campeonato(
        self,
        interaction: discord.Interaction,
        nome: str,
        rank: app_commands.Choice[str],
        formato: app_commands.Choice[str],
        tipo: app_commands.Choice[str],
        organizador: str,
    ):
        chave = _chave(nome)
        dados = ler_campeonatos()
        if chave in dados:
            await interaction.response.send_message(
                f"❌ Já existe um campeonato chamado **{nome}**. Escolha outro nome.", ephemeral=True
            )
            return

        info = {
            "nome": nome,
            "rank": rank.value,
            "formato": formato.value,
            "tipo": tipo.value,
            "organizador": organizador,
            "canal_id": interaction.channel_id,
            "message_id": None,
            "lista_message_id": None,
            "inscritos": {},
        }

        # Responde só pra você, de forma discreta — o anúncio de verdade vai
        # como mensagem própria do bot, sem aparecer como resposta ao seu comando
        await interaction.response.send_message("✅ Campeonato criado!", ephemeral=True)

        canal = interaction.channel
        msg_info = await canal.send(embed=construir_embed_info(info), view=EntrarTorneioView(chave))
        msg_lista = await canal.send(embed=construir_embed_lista(info))

        info["message_id"] = msg_info.id
        info["lista_message_id"] = msg_lista.id
        dados[chave] = info
        salvar_campeonatos(dados)

    @criar_campeonato.error
    async def criar_campeonato_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem criar campeonatos.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro ao criar campeonato: {error}", ephemeral=True)

    # ── /torneiar ────────────────────────────────────────────────────────────
    @app_commands.command(name="torneiar", description="Inscreve uma ou mais pessoas manualmente num campeonato (sem checar rank).")
    @app_commands.describe(
        campeonato="Nome do campeonato",
        membro1="Quem vai ser inscrito",
        membro2="(opcional) mais alguém",
        membro3="(opcional) mais alguém",
        membro4="(opcional) mais alguém",
        membro5="(opcional) mais alguém",
    )
    @app_commands.autocomplete(campeonato=_autocomplete_campeonato)
    @app_commands.checks.has_permissions(administrator=True)
    async def torneiar(
        self,
        interaction: discord.Interaction,
        campeonato: str,
        membro1: discord.Member,
        membro2: discord.Member = None,
        membro3: discord.Member = None,
        membro4: discord.Member = None,
        membro5: discord.Member = None,
    ):
        chave = _chave(campeonato)
        dados = ler_campeonatos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum campeonato chamado **{campeonato}**.", ephemeral=True)
            return

        membros = [m for m in (membro1, membro2, membro3, membro4, membro5) if m is not None]

        inscritos_agora = []
        ja_estavam = []
        for membro in membros:
            if str(membro.id) in info["inscritos"]:
                ja_estavam.append(membro.display_name)
            else:
                info["inscritos"][str(membro.id)] = {"pais": "—"}
                inscritos_agora.append(membro.display_name)

        salvar_campeonatos(dados)
        await _atualizar_lista(self.bot, chave)

        partes = []
        if inscritos_agora:
            partes.append(f"✅ Inscrito(s) em **{info['nome']}**: {', '.join(inscritos_agora)}")
        if ja_estavam:
            partes.append(f"⚠️ Já estavam inscritos (ignorados): {', '.join(ja_estavam)}")

        await interaction.response.send_message("\n".join(partes) or "⚠️ Nada pra fazer.", ephemeral=True)

    @torneiar.error
    async def torneiar_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── /deletar-torneio ─────────────────────────────────────────────────────
    @app_commands.command(name="deletar-torneio", description="Apaga um campeonato (as duas mensagens e todos os inscritos).")
    @app_commands.describe(campeonato="Qual campeonato apagar")
    @app_commands.autocomplete(campeonato=_autocomplete_campeonato)
    @app_commands.checks.has_permissions(administrator=True)
    async def deletar_torneio(self, interaction: discord.Interaction, campeonato: str):
        chave = _chave(campeonato)
        dados = ler_campeonatos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum campeonato chamado **{campeonato}**.", ephemeral=True)
            return

        view = ConfirmarExclusaoView(chave, self.bot)
        await interaction.response.send_message(
            f"⚠️ Tem certeza que quer apagar o campeonato **{info['nome']}**? "
            f"Isso vai apagar as mensagens e **{len(info['inscritos'])} inscrição(ões)**, sem volta.",
            view=view,
            ephemeral=True,
        )

    @deletar_torneio.error
    async def deletar_torneio_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── !destornear <membro> <nome do campeonato> — tira alguém da lista ────
    @commands.command(name="destornear")
    @commands.has_permissions(administrator=True)
    async def destornear(self, ctx: commands.Context, membro: discord.Member, *, nome_campeonato: str):
        """Tira alguém da lista de inscritos de um campeonato.

        Uso: !destornear @pessoa <nome do campeonato>
        """
        chave = _chave(nome_campeonato)
        dados = ler_campeonatos()
        info = dados.get(chave)
        if info is None:
            await ctx.send(f"❌ Não encontrei nenhum campeonato chamado **{nome_campeonato}**.", delete_after=8)
            return

        if str(membro.id) not in info["inscritos"]:
            await ctx.send(f"⚠️ **{membro.display_name}** não está inscrito em **{info['nome']}**.", delete_after=6)
            return

        del info["inscritos"][str(membro.id)]
        salvar_campeonatos(dados)
        await _atualizar_lista(self.bot, chave)

        await ctx.send(f"✅ **{membro.display_name}** foi removido de **{info['nome']}**.", delete_after=8)

    @destornear.error
    async def destornear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Só **Administradores** podem usar este comando.", delete_after=6)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado. Marque a pessoa com `@` ou use o nick certinho.", delete_after=6)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Uso: `!destornear @pessoa <nome do campeonato>`", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Campeonato(bot))
