import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import re

from cogs.backup import ler, salvar
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Loja
#  Arquivo: cogs/loja.py
#
#  Loja de itens do Rocket League (Carros, Decals, Rodas, Boosts, Trails,
#  Explosões de Gol, Hinos, Banners, Itens Especiais), cadastrada à mão
#  pela Staff (não existe API pública oficial da loja do jogo) e exibida
#  num embed organizado por categoria via /loja.
#
#  Guardado em data/loja.json:
#    {
#      "categorias": {"carros": [{"nome":..., "preco":...}], ...},
#      "destaque":   {"nome":..., "preco":..., "categoria":...} | None,
#      "atualizado_em": "dd/mm/aaaa" | None,
#    }
#
#  Sempre que a Staff mexe na loja (adiciona/remove item, define destaque
#  ou limpa pra nova rotação), o bot edita automaticamente a mensagem fixa
#  no canal configurado (CANAL_LOJA_ID) — igual o painel de cogs/players.py.
# ─────────────────────────────────────────────

CANAL_LOJA_ID = 1543811808853229640

MAX_ITENS_POR_CATEGORIA = 15

CATEGORIAS = {
    "carros":        ("🚗", "Carros"),
    "decals":        ("🎨", "Decals"),
    "rodas":         ("⚙️", "Rodas"),
    "boosts":        ("🔥", "Boosts"),
    "trails":        ("💫", "Trails"),
    "explosoes_gol": ("🎆", "Explosões de Gol"),
    "hinos":         ("🎵", "Hinos"),
    "banners":       ("🖼️", "Banners"),
    "especiais":     ("✨", "Itens Especiais"),
}


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


def _hoje_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")


def _preco_numerico(preco: str) -> float:
    """Extrai um valor numérico aproximado de uma string de preço tipo
    '1.100 créditos', '800 créditos', 'R$ 50' — usado só pra ordenar os
    itens da loja do mais caro pro mais barato. Se não achar número
    nenhum, considera 0 (o item vai pro final da lista)."""
    m = re.search(r"[\d][\d.,]*", preco or "")
    if not m:
        return 0.0
    bruto = m.group(0)
    # remove separador de milhar (ponto/vírgula seguido de exatamente 3 dígitos)
    normalizado = re.sub(r"[.,](?=\d{3}(\D|$))", "", bruto)
    normalizado = normalizado.replace(",", ".")
    try:
        return float(normalizado)
    except ValueError:
        return 0.0


def _ordenar_por_preco(itens: list) -> list:
    """Do mais caro pro mais barato — os que não têm preço reconhecível
    (0) ficam no final, na ordem em que foram cadastrados."""
    return sorted(itens, key=lambda it: _preco_numerico(it.get("preco", "")), reverse=True)


def _garantir_loja() -> dict:
    dados = ler("loja")
    dados.setdefault("categorias", {})
    for chave in CATEGORIAS:
        itens = dados["categorias"].setdefault(chave, [])
        dados["categorias"][chave] = _ordenar_por_preco(itens)
    dados.setdefault("destaque", None)
    dados.setdefault("atualizado_em", None)
    return dados


def build_embed(dados: dict) -> discord.Embed:
    embed = discord.Embed(title="🛒  TRYHARDERS RL — LOJA", color=0xD4A843)

    destaque = dados.get("destaque")
    if destaque:
        cat_txt = ""
        if destaque.get("categoria") and destaque["categoria"] in CATEGORIAS:
            emoji_cat, nome_cat = CATEGORIAS[destaque["categoria"]]
            cat_txt = f" ({emoji_cat} {nome_cat})"
        embed.add_field(
            name="🌟  Item em Destaque",
            value=f"**{destaque['nome']}**{cat_txt}\n💰 {destaque['preco']}",
            inline=False,
        )

    tem_item = False
    for chave, (emoji, nome_cat) in CATEGORIAS.items():
        itens = dados["categorias"].get(chave, [])
        if not itens:
            continue
        tem_item = True
        linhas = "\n".join(f"`{i}.` {it['nome']} — 💰 {it['preco']}" for i, it in enumerate(itens, start=1))
        embed.add_field(name=f"{emoji}  {nome_cat}", value=linhas, inline=False)

    if not tem_item and not destaque:
        embed.description = "_A loja ainda não foi configurada. Use `/loja-item-adicionar` para começar._"

    embed.set_footer(text=f"🗓️  Atualização: {dados.get('atualizado_em') or '—'}")
    return embed


def _choices_categoria():
    return [app_commands.Choice(name=f"{emoji} {nome}", value=chave) for chave, (emoji, nome) in CATEGORIAS.items()]


class Loja(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id = None

    async def _atualizar_canal(self):
        canal = self.bot.get_channel(CANAL_LOJA_ID)
        if canal is None:
            print(f"[LOJA] ⚠️ Canal {CANAL_LOJA_ID} não encontrado.")
            return

        dados = _garantir_loja()
        embed = build_embed(dados)

        if self.message_id:
            try:
                msg = await canal.fetch_message(self.message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                self.message_id = None

        async for msg in canal.history(limit=20):
            if msg.author == self.bot.user and msg.embeds and "LOJA" in (msg.embeds[0].title or ""):
                self.message_id = msg.id
                await msg.edit(embed=embed)
                return

        nova = await canal.send(embed=embed)
        self.message_id = nova.id
        print(f"[LOJA] ✅ Painel da loja criado em #{canal.name}.")

    async def _checar_staff(self, interaction: discord.Interaction) -> bool:
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode gerenciar a loja.", ephemeral=True
            )
            return False
        return True

    # ── /loja — mostra a loja atual ──────────────────────────────────────
    @app_commands.command(name="loja", description="Veja a loja atual de itens do Rocket League.")
    async def loja_cmd(self, interaction: discord.Interaction):
        dados = _garantir_loja()
        await interaction.response.send_message(embed=build_embed(dados))

    # ── /loja-item-adicionar ──────────────────────────────────────────────
    @app_commands.command(name="loja-item-adicionar", description="[Staff] Adiciona um item na loja.")
    @app_commands.describe(categoria="Categoria do item", nome="Nome do item", preco="Preço (ex: '1.100 créditos')")
    @app_commands.choices(categoria=_choices_categoria())
    async def loja_item_adicionar(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        nome: str,
        preco: str,
    ):
        if not await self._checar_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        dados = _garantir_loja()
        itens = dados["categorias"][categoria.value]
        if len(itens) >= MAX_ITENS_POR_CATEGORIA:
            await interaction.followup.send(
                f"❌ A categoria **{categoria.name}** já tem {MAX_ITENS_POR_CATEGORIA} itens (limite). "
                f"Remova algum com `/loja-item-remover` antes de adicionar outro.",
                ephemeral=True,
            )
            return

        itens.append({"nome": nome.strip()[:100], "preco": preco.strip()[:50]})
        dados["categorias"][categoria.value] = _ordenar_por_preco(itens)
        dados["atualizado_em"] = _hoje_str()
        salvar("loja", dados)
        await self._atualizar_canal()

        await interaction.followup.send(
            f"✅ Item adicionado em **{categoria.name}**: **{nome.strip()}** — 💰 {preco.strip()}",
            ephemeral=True,
        )
        print(f"[LOJA] ✅ {interaction.user} adicionou '{nome}' em {categoria.value}")

    # ── /loja-item-remover ────────────────────────────────────────────────
    @app_commands.command(name="loja-item-remover", description="[Staff] Remove um item da loja (veja o número com /loja).")
    @app_commands.describe(categoria="Categoria do item", numero="Número do item na categoria (veja com /loja)")
    @app_commands.choices(categoria=_choices_categoria())
    async def loja_item_remover(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        numero: int,
    ):
        if not await self._checar_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        dados = _garantir_loja()
        itens = dados["categorias"][categoria.value]

        if not (1 <= numero <= len(itens)):
            await interaction.followup.send(
                f"❌ Número inválido. A categoria **{categoria.name}** tem {len(itens)} item(ns) — use `/loja` pra conferir.",
                ephemeral=True,
            )
            return

        removido = itens.pop(numero - 1)
        dados["atualizado_em"] = _hoje_str()
        salvar("loja", dados)
        await self._atualizar_canal()

        await interaction.followup.send(
            f"🗑️ Removido de **{categoria.name}**: {removido['nome']} — 💰 {removido['preco']}",
            ephemeral=True,
        )
        print(f"[LOJA] 🗑️ {interaction.user} removeu '{removido['nome']}' de {categoria.value}")

    # ── /loja-destaque ────────────────────────────────────────────────────
    @app_commands.command(name="loja-destaque", description="[Staff] Define o item em destaque da loja.")
    @app_commands.describe(nome="Nome do item em destaque", preco="Preço do item", categoria="Categoria (opcional, só pra exibição)")
    @app_commands.choices(categoria=_choices_categoria())
    async def loja_destaque(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: str,
        categoria: app_commands.Choice[str] = None,
    ):
        if not await self._checar_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        dados = _garantir_loja()
        dados["destaque"] = {
            "nome": nome.strip()[:100],
            "preco": preco.strip()[:50],
            "categoria": categoria.value if categoria else None,
        }
        dados["atualizado_em"] = _hoje_str()
        salvar("loja", dados)
        await self._atualizar_canal()

        await interaction.followup.send(
            f"✅ Destaque da loja definido: **{nome.strip()}** — 💰 {preco.strip()}", ephemeral=True
        )
        print(f"[LOJA] 🌟 {interaction.user} definiu o destaque: {nome}")

    # ── /loja-limpar — zera tudo pra começar uma rotação nova ───────────────
    @app_commands.command(name="loja-limpar", description="[Staff] Limpa toda a loja (todos os itens e o destaque) para uma nova rotação.")
    async def loja_limpar(self, interaction: discord.Interaction):
        if not await self._checar_staff(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        dados = {
            "categorias": {chave: [] for chave in CATEGORIAS},
            "destaque": None,
            "atualizado_em": _hoje_str(),
        }
        salvar("loja", dados)
        await self._atualizar_canal()

        await interaction.followup.send("🧹 Loja limpa! Pronta pra cadastrar a nova rotação.", ephemeral=True)
        print(f"[LOJA] 🧹 {interaction.user} limpou a loja para nova rotação.")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = f"❌ Erro: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Loja(bot))
