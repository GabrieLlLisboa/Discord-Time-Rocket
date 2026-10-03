"""
Função totalmente separada: comando oculto !wuwaud8awduwhauyidh (prefixo).

- Sem descrição/ajuda (não aparece no !help) e não tem lista pública.
- Só funciona para o usuário AUTORIZADO_ID. Para qualquer outra pessoa o
  bot simplesmente ignora, sem responder nada.
- A mensagem com o comando é apagada (o before_invoke do main.py já faz isso)
  e o resultado vai por DM, pra ninguém no canal ver o que foi feito.
- Cria categorias, canais e cargos da estrutura da DPF. É idempotente:
  o que já existir (mesmo nome) é reaproveitado, não duplica.
"""
import asyncio
import unicodedata

import discord
from discord.ext import commands

AUTORIZADO_ID = 1487452210605588592

# ─── Estrutura de canais ─────────────────────────────────────────────────────
ESTRUTURA = [
    ("🏛️ INSTITUCIONAL", ["📌│informações", "📜│regulamento", "📢│anúncios"]),
    ("👮 EFETIVO", ["👥│efetivo", "📋│ausências", "⚠️│advertências", "🏆│promoções"]),
    ("🚔 OPERACIONAL", ["🚨│operações", "📝│relatórios", "🚗│frota", "📍│ocorrências"]),
    ("🛡️ COT", ["📢│cot", "📋│cot-escala", "📝│cot-relatórios"]),
    ("🏢 DELEGACIAS", ["🏢│dpf-central", "🏢│dpf-1", "🏢│dpf-2"]),
    ("🔎 INVESTIGAÇÃO", ["🔍│investigações", "📁│casos", "📝│relatórios"]),
    ("⚖️ CORREGEDORIA", ["📥│denúncias", "⚖️│processos"]),
    ("🎓 ACADEMIA", ["📝│recrutamento", "🎓│treinamentos", "🏅│resultados"]),
    ("🗂️ ADMINISTRAÇÃO", ["📑│requerimentos", "📅│agenda"]),
    ("💬 GERAL", ["💬│chat", "📸│registros", "🤖│comandos"]),
]

# ─── Cargos (do mais alto para o mais baixo) ─────────────────────────────────
CARGOS = [
    # Comando
    ("👑 Diretor-Geral", "#0B1F3A"),
    ("⭐ Diretor", "#123B66"),
    ("🏛️ Superintendente", "#164E78"),
    ("🎖️ Delegado-Chefe", "#1E6FA8"),
    # Delegados
    ("🔷 Delegado Federal", "#2878B5"),
    ("🔹 Delegado Adjunto", "#3D8FC4"),
    # Agentes
    ("🛡️ Agente Especial", "#4A6F8F"),
    ("👮 Agente Federal", "#5C82A3"),
    ("🔰 Agente", "#7199B8"),
    # COT
    ("🔥 Comandante COT", "#C45A00"),
    ("⚔️ Operador COT", "#E07818"),
    # Especializações
    ("🧠 Inteligência", "#55418A"),
    ("🔬 Perito Criminal", "#287A52"),
    ("💻 Agente Cibernético", "#208A9A"),
    # Administração
    ("⚖️ Corregedoria", "#9B2020"),
    ("📋 Ouvidoria", "#795548"),
    ("🗂️ Administrativo", "#68727C"),
    # Formação
    ("🎓 Instrutor", "#B88A00"),
    ("📚 Aluno", "#D1A72C"),
    ("🪪 Recruta", "#89939C"),
    ("👤 Civil", "#4B4B4B"),
]
SEM_DESTAQUE = {"👤 Civil"}  # não aparece separado na lista de membros


def _normaliza(nome: str) -> str:
    """Compara nomes ignorando acento, maiúsculas e espaço/hífen, pra achar
    canais/categorias que já existem (inclusive criados antes, sem acento)."""
    sem = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    return sem.lower().replace(" ", "-")


class EstruturaSecreta(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="wuwaud8awduwhauyidh", hidden=True)
    @commands.guild_only()
    async def estrutura(self, ctx: commands.Context):
        if ctx.author.id != AUTORIZADO_ID:
            return  # ignora em silêncio

        async def responder(texto: str):
            try:
                await ctx.author.send(texto)
            except discord.HTTPException:
                await ctx.send(texto, delete_after=20)

        guild = ctx.guild

        cargos_criados = cargos_existentes = 0
        cats_criadas = canais_criados = canais_existentes = renomeados = 0

        try:
            # Cargos: cada cargo novo entra no FUNDO da lista, então criamos
            # na ordem (Diretor-Geral primeiro) e depois ajustamos as posições
            # pra garantir a hierarquia certa, inclusive de cargos já existentes.
            objetos = []
            for nome, cor in CARGOS:
                cargo = discord.utils.get(guild.roles, name=nome)
                if cargo is not None:
                    cargos_existentes += 1
                else:
                    cargo = await guild.create_role(
                        name=nome,
                        colour=discord.Colour(int(cor.lstrip("#"), 16)),
                        hoist=nome not in SEM_DESTAQUE,
                        mentionable=False,
                        reason="Estrutura DPF",
                    )
                    cargos_criados += 1
                    await asyncio.sleep(0.6)
                objetos.append(cargo)

            # Mantém o bloco de cargos onde está (base = posição mais baixa
            # entre eles) e só reordena entre si, do topo (Diretor-Geral) ao fundo.
            teto = guild.me.top_role.position - 1
            base = max(1, min(min(c.position for c in objetos), teto - len(objetos) + 1))
            posicoes = {c: base + (len(objetos) - 1 - i) for i, c in enumerate(objetos)}
            if max(posicoes.values()) <= teto:
                await guild.edit_role_positions(posicoes, reason="Estrutura DPF")

            # Categorias e canais (reaproveita e renomeia os que já existiam sem acento)
            for nome_cat, canais in ESTRUTURA:
                categoria = next(
                    (c for c in guild.categories if _normaliza(c.name) == _normaliza(nome_cat)),
                    None,
                )
                if categoria is None:
                    categoria = await guild.create_category(nome_cat, reason="Estrutura DPF")
                    cats_criadas += 1
                    await asyncio.sleep(0.6)
                elif categoria.name != nome_cat:
                    await categoria.edit(name=nome_cat, reason="Estrutura DPF")
                    renomeados += 1
                    await asyncio.sleep(0.6)

                existentes = {_normaliza(c.name): c for c in categoria.text_channels}
                for nome_canal in canais:
                    canal = existentes.get(_normaliza(nome_canal))
                    if canal is None:
                        await guild.create_text_channel(
                            nome_canal, category=categoria, reason="Estrutura DPF"
                        )
                        canais_criados += 1
                        await asyncio.sleep(0.6)
                    else:
                        canais_existentes += 1
                        if canal.name != nome_canal.lower().replace(" ", "-"):
                            await canal.edit(name=nome_canal, reason="Estrutura DPF")
                            renomeados += 1
                            await asyncio.sleep(0.6)

        except discord.Forbidden:
            await responder(
                "❌ Sem permissão. O bot precisa de **Gerenciar Canais** e **Gerenciar Cargos**, "
                "e o cargo dele precisa estar acima dos cargos criados.\n"
                f"Já criado: {cargos_criados} cargos, {cats_criadas} categorias, {canais_criados} canais.",
            )
            return
        except discord.HTTPException as e:
            await responder(
                f"❌ Erro do Discord: `{e}`\n"
                f"Já criado: {cargos_criados} cargos, {cats_criadas} categorias, {canais_criados} canais. "
                "Rode de novo para continuar (não duplica).",
            )
            return

        await responder(
            f"✅ Pronto.\n"
            f"Cargos: {cargos_criados} criados, {cargos_existentes} já existiam.\n"
            f"Categorias: {cats_criadas} criadas.\n"
            f"Canais: {canais_criados} criados, {canais_existentes} já existiam.\n"
            f"Renomeados (acentos): {renomeados}.",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EstruturaSecreta(bot))
