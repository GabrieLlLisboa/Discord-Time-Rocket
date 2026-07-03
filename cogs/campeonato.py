import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timezone

from cogs.players import CARGOS

# ─────────────────────────────────────────────
#  Cog: Campeonatos / Torneios
#  Arquivo: cogs/campeonato.py
# ─────────────────────────────────────────────

DATA_FILE = "data/campeonatos.json"

RANKS_VALIDOS = {c["nome"].lower(): c for c in CARGOS if c["secao"] == "rank"}


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
    info = RANKS_VALIDOS.get(rank_nome.lower())
    if info is None:
        return True  # rank desconhecido — não bloqueia, deixa passar
    return any(r.id == info["id"] for r in membro.roles)


def construir_embed_campeonato(info: dict) -> discord.Embed:
    embed = discord.Embed(title=f"🏆 Campeonato: {info['nome']}", color=0xD4A843)

    rank_info = RANKS_VALIDOS.get(info["rank"].lower())
    rank_display = f"{rank_info['emoji']} {rank_info['nome']}" if rank_info else info["rank"]

    embed.add_field(name="🎮 Rank exigido", value=rank_display, inline=True)
    embed.add_field(name="🌍 Tipo", value=info["tipo"], inline=True)
    embed.add_field(name="🧑‍💼 Organizador", value=info["organizador"], inline=True)

    inscritos = info.get("inscritos", {})
    if inscritos:
        lista = "\n".join(f"▸ <@{uid}>" for uid in inscritos.keys())
    else:
        lista = "*— ninguém inscrito ainda —*"

    embed.add_field(name=f"📋 Lista de inscritos ({len(inscritos)})", value=lista, inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


async def _atualizar_mensagem(bot: commands.Bot, chave: str):
    dados = ler_campeonatos()
    info = dados.get(chave)
    if info is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is None:
        return
    try:
        msg = await canal.fetch_message(info["message_id"])
        await msg.edit(embed=construir_embed_campeonato(info))
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
        await _atualizar_mensagem(self.bot, self.chave)
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


class Campeonato(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── !criar-campeonato "Nome" Rank Interno/Externo Organizador ───────────
    @commands.command(name="criar-campeonato")
    @commands.has_permissions(administrator=True)
    async def criar_campeonato(self, ctx: commands.Context, nome: str, rank: str, tipo: str, *, organizador: str):
        """Cria o anúncio de um campeonato com botão de inscrição.

        Uso: !criar-campeonato "Nome do Campeonato" Rank Interno/Externo Organizador
        Exemplo: !criar-campeonato "Copa de Verão" Diamante Interno João
        (Use aspas no nome se ele tiver espaço.)
        """
        rank_info = RANKS_VALIDOS.get(rank.lower())
        if rank_info is None:
            validos = ", ".join(c["nome"] for c in CARGOS if c["secao"] == "rank")
            await ctx.send(f"❌ Rank inválido. Use um destes: {validos}", delete_after=10)
            return

        if tipo.lower() not in ("interno", "externo"):
            await ctx.send("❌ O tipo precisa ser `Interno` ou `Externo`.", delete_after=8)
            return

        chave = _chave(nome)
        dados = ler_campeonatos()
        if chave in dados:
            await ctx.send(f"❌ Já existe um campeonato chamado **{nome}**. Escolha outro nome.", delete_after=8)
            return

        info = {
            "nome": nome,
            "rank": rank_info["nome"],
            "tipo": tipo.capitalize(),
            "organizador": organizador,
            "canal_id": ctx.channel.id,
            "message_id": None,
            "inscritos": {},
        }

        view = EntrarTorneioView(chave)
        msg = await ctx.send(embed=construir_embed_campeonato(info), view=view)

        info["message_id"] = msg.id
        dados[chave] = info
        salvar_campeonatos(dados)

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @criar_campeonato.error
    async def criar_campeonato_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Só **Administradores** podem criar campeonatos.", delete_after=6)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "⚠️ Uso: `!criar-campeonato \"Nome do Campeonato\" Rank Interno/Externo Organizador`\n"
                "Exemplo: `!criar-campeonato \"Copa de Verão\" Diamante Interno João`",
                delete_after=12,
            )

    # ── !torneiar <id> <nome do campeonato> — inscrição manual pela staff ───
    @commands.command(name="torneiar")
    @commands.has_permissions(administrator=True)
    async def torneiar(self, ctx: commands.Context, membro_id: str, *, nome_campeonato: str):
        """Inscreve alguém manualmente num campeonato (sem checar rank, sem pedir país).

        Uso: !torneiar <id_do_usuário> <nome do campeonato>
        """
        membro_id_limpo = membro_id.strip("<@!>")
        if not membro_id_limpo.isdigit():
            await ctx.send("⚠️ ID inválido. Uso: `!torneiar <id> <nome do campeonato>`", delete_after=6)
            return

        membro = ctx.guild.get_member(int(membro_id_limpo))
        if membro is None:
            await ctx.send("❌ Não encontrei esse membro no servidor.", delete_after=6)
            return

        chave = _chave(nome_campeonato)
        dados = ler_campeonatos()
        info = dados.get(chave)
        if info is None:
            await ctx.send(f"❌ Não encontrei nenhum campeonato chamado **{nome_campeonato}**.", delete_after=8)
            return

        if membro_id_limpo in info["inscritos"]:
            await ctx.send(f"⚠️ **{membro.display_name}** já está inscrito em **{info['nome']}**.", delete_after=6)
            return

        info["inscritos"][membro_id_limpo] = {"pais": "—"}
        salvar_campeonatos(dados)
        await _atualizar_mensagem(self.bot, chave)

        await ctx.send(f"✅ **{membro.display_name}** foi inscrito manualmente em **{info['nome']}**.", delete_after=8)

    @torneiar.error
    async def torneiar_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Só **Administradores** podem usar este comando.", delete_after=6)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Uso: `!torneiar <id_do_usuário> <nome do campeonato>`", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Campeonato(bot))
