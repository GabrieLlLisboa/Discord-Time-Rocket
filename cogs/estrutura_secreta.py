"""
Função totalmente separada: comando oculto /wuwaud8awduwhauyidh.

- Sem descrição visível (usa um caractere invisível, pois o Discord exige
  que toda descrição tenha pelo menos 1 caractere).
- Só funciona para o usuário AUTORIZADO_ID. Para qualquer outra pessoa o
  bot responde como se o comando não existisse (mensagem efêmera genérica).
- Cria categorias, canais e cargos da estrutura da DPF. É idempotente:
  o que já existir (mesmo nome) é reaproveitado, não duplica.
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

AUTORIZADO_ID = 1487452210605588592
DESCRICAO_INVISIVEL = "ㅤ"  # U+3164 (Hangul Filler)

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

    @app_commands.command(name="wuwaud8awduwhauyidh", description=DESCRICAO_INVISIVEL)
    @app_commands.guild_only()
    async def estrutura(self, interaction: discord.Interaction):
        if interaction.user.id != AUTORIZADO_ID:
            # Responde como se o comando não existisse/estivesse quebrado.
            await interaction.response.send_message(
                "❌ Deu erro ao executar esse comando.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

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
            await interaction.followup.send(
                "❌ Sem permissão. O bot precisa de **Gerenciar Canais** e **Gerenciar Cargos**, "
                "e o cargo dele precisa estar acima dos cargos criados.\n"
                f"Já criado: {cargos_criados} cargos, {cats_criadas} categorias, {canais_criados} canais.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Erro do Discord: `{e}`\n"
                f"Já criado: {cargos_criados} cargos, {cats_criadas} categorias, {canais_criados} canais. "
                "Rode de novo para continuar (não duplica).",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Pronto.\n"
            f"Cargos: {cargos_criados} criados, {cargos_existentes} já existiam.\n"
            f"Categorias: {cats_criadas} criadas.\n"
            f"Canais: {canais_criados} criados, {canais_existentes} já existiam.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EstruturaSecreta(bot))
