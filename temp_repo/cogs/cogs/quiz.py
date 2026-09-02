import discord
from discord.ext import commands
from discord import app_commands
import random
import time

from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Quiz de Rocket League
#  Arquivo: cogs/quiz.py
#  /quiz            — pergunta aleatória (times, mapas, mecânicas)
#  /quiz_ranking    — ranking de quem mais acerta
#  /quiz_reset      — zera o ranking (admin)
# ─────────────────────────────────────────────

RANKING_PATH = "data/quiz_ranking.json"

# Tempo (segundos) que a pergunta fica aberta pra responder
TEMPO_RESPOSTA = 25

# ── Banco de perguntas ──────────────────────────────────────────────────────
# categoria: "times" | "mapas" | "mecanicas"
PERGUNTAS = [
    # ── Times ──
    {
        "categoria": "times",
        "pergunta": "Qual time venceu o Rocket League Championship (RLCS) World Championship de 2023?",
        "opcoes": ["Karmine Corp", "Team BDS", "G2 Esports", "Complexity Gaming"],
        "correta": 0,
    },
    {
        "categoria": "times",
        "pergunta": "Qual desses times é conhecido por ser brasileiro?",
        "opcoes": ["Team Vitality", "FURIA", "Moist Esports", "Dignitas"],
        "correta": 1,
    },
    {
        "categoria": "times",
        "pergunta": "Qual jogador é famoso pelo apelido 'Squishy' e já jogou pela NRG?",
        "opcoes": ["Jstn", "GarrettG", "Squishy", "Firstkiller"],
        "correta": 2,
    },
    {
        "categoria": "times",
        "pergunta": "Team BDS é organização de qual região competitiva?",
        "opcoes": ["Oceania", "América do Sul", "Europa", "América do Norte"],
        "correta": 2,
    },
    {
        "categoria": "times",
        "pergunta": "Qual jogador brasileiro ficou famoso jogando por times como FaZe Clan e Furia?",
        "opcoes": ["yanxnz", "CooL", "Aztral", "Kaydop"],
        "correta": 1,
    },
    # ── Mapas ──
    {
        "categoria": "mapas",
        "pergunta": "Qual é o mapa padrão/clássico do Rocket League, usado desde o lançamento?",
        "opcoes": ["Neo Tokyo", "DFH Stadium", "Champions Field", "Urban Central"],
        "correta": 1,
    },
    {
        "categoria": "mapas",
        "pergunta": "Qual mapa tem tema futurista japonês, com um layout dividido em duas áreas conectadas por um túnel?",
        "opcoes": ["Neo Tokyo", "Beckwith Park", "Mannfield", "Utopia Coliseum"],
        "correta": 0,
    },
    {
        "categoria": "mapas",
        "pergunta": "Qual mapa é ambientado num estádio de futebol americano?",
        "opcoes": ["Champions Field", "Wasteland", "Urban Central", "Farmstead"],
        "correta": 0,
    },
    {
        "categoria": "mapas",
        "pergunta": "Qual desses mapas NÃO existe no Rocket League?",
        "opcoes": ["Starbase ARC", "DFH Stadium", "Solar Circuit", "Ocean Drive"],
        "correta": 3,
    },
    {
        "categoria": "mapas",
        "pergunta": "Qual mapa possui uma variação noturna chamada 'Mannfield (Night)'?",
        "opcoes": ["Mannfield", "Urban Central", "Beckwith Park", "Neo Tokyo"],
        "correta": 0,
    },
    # ── Mecânicas ──
    {
        "categoria": "mecanicas",
        "pergunta": "Como se chama a mecânica de bater a bola no ar usando o carro virado de cabeça para baixo?",
        "opcoes": ["Ceiling shot", "Air dribble", "Musty flick", "Fast aerial"],
        "correta": 2,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "O que é um 'flip reset'?",
        "opcoes": [
            "Recarregar o boost instantaneamente",
            "Recuperar a habilidade de dar flip ao tocar a bola no ar",
            "Resetar a posição do carro após um gol",
            "Trocar de carro durante a partida",
        ],
        "correta": 1,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "Como se chama a técnica de acelerar no ar sem gastar tempo alinhando o carro antes, otimizando velocidade?",
        "opcoes": ["Fast aerial", "Ceiling shot", "Wave dash", "Half flip"],
        "correta": 0,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "O 'half flip' é usado principalmente para quê?",
        "opcoes": [
            "Fazer um gol de assinatura",
            "Virar o carro rapidamente e ganhar velocidade para trás",
            "Roubar o boost do adversário",
            "Pular mais alto que o normal",
        ],
        "correta": 1,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "Quanto tempo (aproximadamente) o boost grande (pad grande) demora para reaparecer após ser coletado?",
        "opcoes": ["4 segundos", "10 segundos", "30 segundos", "1 minuto"],
        "correta": 1,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "Como se chama o movimento de bater na bola duas vezes seguidas no ar, no mesmo dribble?",
        "opcoes": ["Double tap", "Redirect", "Flick", "Air roll shot"],
        "correta": 0,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "Qual é o nome do recurso que permite girar o carro livremente no ar sem alterar a trajetória?",
        "opcoes": ["Boost", "Air roll", "Powerslide", "Dodge"],
        "correta": 1,
    },
    {
        "categoria": "mecanicas",
        "pergunta": "O que é 'demolir' (demo) um adversário?",
        "opcoes": [
            "Marcar um gol contra ele",
            "Destruir o carro dele batendo em alta velocidade",
            "Roubar o boost dele",
            "Bloquear o chute dele",
        ],
        "correta": 1,
    },
]


# ── Ranking (persistência) ──────────────────────────────────────────────────
def ler_ranking() -> dict:
    return ler_json(RANKING_PATH, {})


def salvar_ranking(dados: dict) -> None:
    salvar_json(RANKING_PATH, dados)


def registrar_resposta(user_id: int, nome: str, acertou: bool) -> None:
    ranking = ler_ranking()
    sid = str(user_id)
    if sid not in ranking:
        ranking[sid] = {"nome": nome, "acertos": 0, "erros": 0}

    ranking[sid]["nome"] = nome  # mantém o nome sempre atualizado
    if acertou:
        ranking[sid]["acertos"] += 1
    else:
        ranking[sid]["erros"] += 1

    salvar_ranking(ranking)


# ── View com os botões de resposta ──────────────────────────────────────────
LETRAS = ["🇦", "🇧", "🇨", "🇩"]


class QuizView(discord.ui.View):
    def __init__(self, pergunta: dict, autor_id: int | None = None):
        super().__init__(timeout=TEMPO_RESPOSTA)
        self.pergunta = pergunta
        self.respondidos: dict[int, int] = {}  # user_id -> índice escolhido
        self.nomes: dict[int, str] = {}  # user_id -> nome de exibição (ordem de resposta)
        self.message: discord.Message | None = None

        for i, opcao in enumerate(pergunta["opcoes"]):
            self.add_item(QuizButton(i, f"{LETRAS[i]} {opcao}"))

    async def registrar_escolha(self, interaction: discord.Interaction, indice: int):
        user_id = interaction.user.id

        if user_id in self.respondidos:
            await interaction.response.send_message(
                "⚠️ Você já respondeu essa pergunta!", ephemeral=True
            )
            return

        self.respondidos[user_id] = indice
        self.nomes[user_id] = interaction.user.display_name
        acertou = indice == self.pergunta["correta"]
        registrar_resposta(user_id, interaction.user.display_name, acertou)

        if acertou:
            await interaction.response.send_message("✅ Acertou! Boa!", ephemeral=True)
        else:
            correta_texto = self.pergunta["opcoes"][self.pergunta["correta"]]
            await interaction.response.send_message(
                f"❌ Errou! A resposta certa era: **{correta_texto}**", ephemeral=True
            )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message is None:
            return

        correta_texto = self.pergunta["opcoes"][self.pergunta["correta"]]

        embed = self.message.embeds[0]
        embed.color = discord.Color.blurple()

        if self.respondidos:
            acertaram = [
                uid for uid, idx in self.respondidos.items()
                if idx == self.pergunta["correta"]
            ]
            resumo = f"✅ **{len(acertaram)}** de **{len(self.respondidos)}** responderam corretamente."

            linhas = []
            for uid, idx in self.respondidos.items():
                nome = self.nomes.get(uid, "Desconhecido")
                if idx == self.pergunta["correta"]:
                    linhas.append(f"✅ **{nome}** — Acertou")
                else:
                    linhas.append(f"❌ **{nome}** — Errou")

            # Discord limita cada campo de embed a 1024 caracteres — se
            # muita gente responder, mostra só os primeiros e resume o resto.
            LIMITE_EXIBIDO = 20
            if len(linhas) > LIMITE_EXIBIDO:
                restantes = len(linhas) - LIMITE_EXIBIDO
                linhas = linhas[:LIMITE_EXIBIDO] + [f"*...e mais {restantes} pessoa(s).*"]

            embed.add_field(
                name="⏰ Tempo esgotado!",
                value=f"A resposta certa era: **{correta_texto}**\n{resumo}",
                inline=False,
            )
            embed.add_field(
                name="📋 Lista de quem respondeu",
                value="\n".join(linhas),
                inline=False,
            )
        else:
            embed.add_field(
                name="⏰ Tempo esgotado!",
                value=f"A resposta certa era: **{correta_texto}**\n😴 Ninguém respondeu a tempo.",
                inline=False,
            )

        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class QuizButton(discord.ui.Button):
    def __init__(self, indice: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction):
        view: QuizView = self.view
        await view.registrar_escolha(interaction, self.indice)


CATEGORIA_EMOJI = {
    "times": "🏆",
    "mapas": "🗺️",
    "mecanicas": "🎮",
}


class Quiz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /quiz ────────────────────────────────────────────────────────────
    @app_commands.command(name="quiz", description="Responda uma pergunta sobre Rocket League (times, mapas, mecânicas).")
    @app_commands.describe(categoria="Filtrar por categoria (opcional)")
    @app_commands.choices(categoria=[
        app_commands.Choice(name="Times", value="times"),
        app_commands.Choice(name="Mapas", value="mapas"),
        app_commands.Choice(name="Mecânicas", value="mecanicas"),
    ])
    async def quiz(self, interaction: discord.Interaction, categoria: app_commands.Choice[str] = None):
        pool = PERGUNTAS
        if categoria is not None:
            pool = [p for p in PERGUNTAS if p["categoria"] == categoria.value]

        pergunta = random.choice(pool)
        emoji_cat = CATEGORIA_EMOJI.get(pergunta["categoria"], "❓")

        embed = discord.Embed(
            title=f"{emoji_cat} Quiz de Rocket League",
            description=f"**{pergunta['pergunta']}**",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Opções",
            value="\n".join(f"{LETRAS[i]} {op}" for i, op in enumerate(pergunta["opcoes"])),
            inline=False,
        )
        embed.set_footer(text=f"Você tem {TEMPO_RESPOSTA}s para responder • Categoria: {pergunta['categoria'].capitalize()}")

        view = QuizView(pergunta)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    # ── /quiz_ranking ────────────────────────────────────────────────────
    @app_commands.command(name="quiz_ranking", description="Veja o ranking de quem mais acerta no Quiz de Rocket League.")
    async def quiz_ranking(self, interaction: discord.Interaction):
        ranking = ler_ranking()

        if not ranking:
            await interaction.response.send_message(
                "📊 Ainda não há dados no ranking. Jogue com `/quiz`!", ephemeral=True
            )
            return

        # Ordena por acertos (desc), depois por menor nº de erros
        colocados = sorted(
            ranking.items(),
            key=lambda item: (-item[1]["acertos"], item[1]["erros"]),
        )[:10]

        medalhas = ["🥇", "🥈", "🥉"]
        linhas = []
        for i, (_, dados) in enumerate(colocados):
            acertos = dados["acertos"]
            erros = dados["erros"]
            total = acertos + erros
            aproveitamento = (acertos / total * 100) if total else 0
            posicao = medalhas[i] if i < 3 else f"`#{i + 1}`"
            linhas.append(
                f"{posicao} **{dados['nome']}** — ✅ {acertos} acertos "
                f"| ❌ {erros} erros | 📈 {aproveitamento:.0f}%"
            )

        embed = discord.Embed(
            title="🏆 Ranking do Quiz de Rocket League",
            description="\n".join(linhas),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Jogue mais partidas do quiz com /quiz")
        await interaction.response.send_message(embed=embed)

    # ── /quiz_reset (staff) ──────────────────────────────────────────────
    @app_commands.command(name="quiz_reset", description="[Staff] Zera o ranking do quiz.")
    @app_commands.checks.has_permissions(administrator=True)
    async def quiz_reset(self, interaction: discord.Interaction):
        salvar_ranking({})
        await interaction.response.send_message("🗑️ Ranking do quiz zerado com sucesso.", ephemeral=True)

    @quiz_reset.error
    async def quiz_reset_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar esse comando.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Quiz(bot))
