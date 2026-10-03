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

import discord
from discord.ext import commands

AUTORIZADO_ID = 1487452210605588592

# ─── Estrutura de canais ─────────────────────────────────────────────────────
ESTRUTURA = [
    ("🏛️ INSTITUCIONAL", ["📌│informacoes", "📜│regulamento", "📢│anuncios"]),
    ("👮 EFETIVO", ["👥│efetivo", "📋│ausencias", "⚠️│advertencias", "🏆│promocoes"]),
    ("🚔 OPERACIONAL", ["🚨│operacoes", "📝│relatorios", "🚗│frota", "📍│ocorrencias"]),
    ("🛡️ COT", ["📢│cot", "📋│cot-escala", "📝│cot-relatorios"]),
    ("🏢 DELEGACIAS", ["🏢│dpf-central", "🏢│dpf-1", "🏢│dpf-2"]),
    ("🔎 INVESTIGACAO", ["🔍│investigacoes", "📁│casos", "📝│relatorios"]),
    ("⚖️ CORREGEDORIA", ["📥│denuncias", "⚖️│processos"]),
    ("🎓 ACADEMIA", ["📝│recrutamento", "🎓│treinamentos", "🏅│resultados"]),
    ("🗂️ ADMINISTRACAO", ["📑│requerimentos", "📅│agenda"]),
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
    """Discord converte nomes de canal de texto para minúsculas e troca
    espaços por hífen; normalizamos igual pra comparar sem duplicar."""
    return nome.lower().replace(" ", "-")


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
        cats_criadas = canais_criados = canais_existentes = 0

        try:
            # Cargos: cria do mais baixo pro mais alto, assim o Diretor-Geral
            # termina no topo da hierarquia (novo cargo entra logo acima do
            # anterior, sempre abaixo do cargo do bot).
            for nome, cor in reversed(CARGOS):
                if discord.utils.get(guild.roles, name=nome):
                    cargos_existentes += 1
                    continue
                await guild.create_role(
                    name=nome,
                    colour=discord.Colour(int(cor.lstrip("#"), 16)),
                    hoist=nome not in SEM_DESTAQUE,
                    mentionable=False,
                    reason="Estrutura DPF",
                )
                cargos_criados += 1
                await asyncio.sleep(0.6)

            # Categorias e canais
            for nome_cat, canais in ESTRUTURA:
                categoria = discord.utils.get(guild.categories, name=nome_cat)
                if categoria is None:
                    categoria = await guild.create_category(nome_cat, reason="Estrutura DPF")
                    cats_criadas += 1
                    await asyncio.sleep(0.6)

                existentes = {_normaliza(c.name) for c in categoria.text_channels}
                for nome_canal in canais:
                    if _normaliza(nome_canal) in existentes:
                        canais_existentes += 1
                        continue
                    await guild.create_text_channel(
                        nome_canal, category=categoria, reason="Estrutura DPF"
                    )
                    canais_criados += 1
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
            f"Canais: {canais_criados} criados, {canais_existentes} já existiam.",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EstruturaSecreta(bot))
