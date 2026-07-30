import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
import time
from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Autopilot
#  Arquivo: cogs/autopilot.py
#  O bot manda mensagens automáticas sozinho, de tempos em tempos, em dois
#  canais fixos e independentes:
#   - CANAL_GERAL_ID -> só curiosidades aleatórias (assuntos gerais)
#   - CANAL_RL_ID    -> só curiosidades de Rocket League
#  Cada canal tem seu próprio agendamento (3h a 5h, sorteado).
# ─────────────────────────────────────────────

CONFIG_PATH = "data/autopilot.json"

# Canal só de curiosidades de Rocket League — intervalo de 30 a 60 minutos.
CANAL_RL_ID = 1511898323840405655
INTERVALO_RL_MIN = 30
INTERVALO_RL_MAX = 60

# Canal só de curiosidades aleatórias (assuntos gerais) — intervalo de 3h a 4h.
CANAL_GERAL_ID = 1511910275618443314
INTERVALO_GERAL_MIN = 180
INTERVALO_GERAL_MAX = 240

CURIOSIDADES_RL = [
    "📚 Você sabia? O Rocket League foi lançado em 2015 e é sucessor espiritual do jogo 'Supersonic Acrobatic Rocket-Powered Battle-Cars'.",
    "📚 Curiosidade: o boost total do carro dura cerca de 10 segundos de uso contínuo em linha reta.",
    "📚 Você sabia? Os pads de boost pequenos dão 12 de boost e os grandes enchem o tanque (100).",
    "📚 Curiosidade: o Rocket League se tornou free-to-play em setembro de 2020.",
    "📚 Você sabia? O RLCS (Rocket League Championship Series) é a principal liga profissional do jogo desde 2016.",
    "📚 Curiosidade: existem mais de 15 mapas diferentes no modo competitivo padrão ao longo da história do jogo.",
    "📚 Você sabia? Um 'ceiling shot' usa o teto do mapa pra pegar impulso antes de finalizar — é uma das mecânicas mais avançadas.",
    "🚀 Você sabia que o criador do flip reset está no nosso servidor? É o **fyshokid**! 👀",
    "🏆 Curiosidade RLCS: alguns jogadores acumulam anos de campeonato sem nunca terem levantado um troféu mundial — a pressão no cenário competitivo é gigante.",
    "🥇 Curiosidade RLCS: os times europeus dominam boa parte dos títulos mundiais da história da competição.",
    "📈 Você sabia? Vários jogadores profissionais de RLCS começaram a competir ainda na adolescência, alguns com menos de 16 anos.",
    "🌟 Curiosidade: o cenário competitivo de Rocket League tem verdadeiros prodígios que já jogavam em nível profissional antes mesmo de terem carteira de motorista.",
    "🎲 Curiosidade aleatória: sabia que dá pra jogar Rocket League com o carro andando de ré o jogo inteiro? Ninguém faz isso, mas dá.",
]

CURIOSIDADES_GERAIS = [
    "🐙 Você sabia? O polvo tem três corações. Dois bombeiam sangue para as brânquias, e um para o resto do corpo.",
    "🍌 Curiosidade: a banana é uma baga, mas o morango não é considerado uma baga pela botânica.",
    "🌍 Você sabia? A Terra gira a cerca de 1.670 km/h no Equador, mas como tudo gira junto, nós não sentimos.",
    "🦒 Curiosidade: as girafas têm o mesmo número de vértebras no pescoço que os humanos: sete. Só que são muito maiores.",
    "🦈 Você sabia? Tubarões existem há mais tempo do que as árvores. Eles surgiram há cerca de 400 milhões de anos, enquanto as primeiras árvores apareceram há cerca de 350 milhões de anos.",
    "🥜 Curiosidade: amendoim não é uma noz. Ele faz parte da família das leguminosas, como o feijão.",
    "🍯 Você sabia? O mel nunca estraga. Foram encontrados potes de mel em tumbas egípcias com mais de 3.000 anos ainda comestíveis.",
    "🐝 Curiosidade: as abelhas conseguem reconhecer rostos humanos, mesmo tendo um cérebro do tamanho de uma semente.",
    "🌋 Você sabia? Existem mais estrelas no universo do que grãos de areia em todas as praias e desertos da Terra juntos.",
    "🧠 Curiosidade: o cérebro humano usa cerca de 20% de toda a energia que o corpo consome, mesmo pesando só uns 2% do peso total.",
    "🐌 Você sabia? Alguns caracóis conseguem dormir por até 3 anos seguidos, dependendo das condições do ambiente.",
    "🦴 Curiosidade: os ossos humanos são, proporcionalmente, mais resistentes que o aço — pra sustentar o mesmo peso, pesam bem menos.",
    "🍇 Você sabia? Uvas podem soltar faíscas se colocadas no micro-ondas, por causa da forma como concentram energia eletromagnética.",
    "🐧 Curiosidade: os pinguins-imperador conseguem mergulhar a mais de 500 metros de profundidade pra caçar.",
]

# Configuração de cada canal fixo do autopilot.
CANAIS = {
    CANAL_GERAL_ID: {"nome": "geral", "mensagens": CURIOSIDADES_GERAIS, "intervalo_min": INTERVALO_GERAL_MIN, "intervalo_max": INTERVALO_GERAL_MAX},
    CANAL_RL_ID: {"nome": "rocket_league", "mensagens": CURIOSIDADES_RL, "intervalo_min": INTERVALO_RL_MIN, "intervalo_max": INTERVALO_RL_MAX},
}


def ler_config() -> dict:
    """Estrutura salva em disco:
    {
      "ativo": True,
      "canais": {
         "<canal_id>": {"proximo_envio_ts": 123456.0}
      }
    }
    """
    return ler_json(CONFIG_PATH, {"ativo": True, "canais": {}})


def salvar_config(dados: dict) -> None:
    salvar_json(CONFIG_PATH, dados)


class Autopilot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autopilot_loop.start()

    def cog_unload(self):
        self.autopilot_loop.cancel()

    @tasks.loop(minutes=1)
    async def autopilot_loop(self):
        await self.bot.wait_until_ready()

        config = ler_config()
        if not config.get("ativo", True):
            return

        canais_cfg = config.setdefault("canais", {})
        agora = time.time()
        precisa_salvar = False

        for canal_id in CANAIS:
            chave = str(canal_id)
            estado = canais_cfg.setdefault(chave, {})
            proximo_ts = estado.get("proximo_envio_ts")

            if not proximo_ts:
                # Primeira vez rodando pra esse canal — agenda e segue.
                self._agendar_proximo(canal_id, estado)
                precisa_salvar = True
                continue

            if agora >= proximo_ts:
                try:
                    await self._enviar_mensagem(canal_id)
                except Exception as e:
                    # Uma falha pontual (canal deletado, sem permissão, etc.)
                    # não pode derrubar o loop pro resto da vida do processo.
                    print(f"[AUTOPILOT] ⚠️ Erro ao enviar mensagem no canal {canal_id}: {e}")
                finally:
                    self._agendar_proximo(canal_id, estado)
                    precisa_salvar = True

        if precisa_salvar:
            salvar_config(config)

    def _agendar_proximo(self, canal_id: int, estado: dict) -> None:
        """Sorteia o intervalo (específico de cada canal) até a próxima
        mensagem e salva o timestamp absoluto, pra sobreviver a reinícios
        do bot."""
        cfg_canal = CANAIS[canal_id]
        intervalo_minutos = random.randint(cfg_canal["intervalo_min"], cfg_canal["intervalo_max"])
        estado["proximo_envio_ts"] = time.time() + (intervalo_minutos * 60)

    @autopilot_loop.before_loop
    async def before_autopilot_loop(self):
        await self.bot.wait_until_ready()
        config = ler_config()
        canais_cfg = config.setdefault("canais", {})
        mudou = False
        for canal_id in CANAIS:
            chave = str(canal_id)
            estado = canais_cfg.setdefault(chave, {})
            if not estado.get("proximo_envio_ts"):
                self._agendar_proximo(canal_id, estado)
                mudou = True
        if mudou:
            salvar_config(config)

    async def _enviar_mensagem(self, canal_id: int):
        canal = self.bot.get_channel(canal_id)
        if canal is None:
            print(f"[AUTOPILOT] ⚠️ Canal {canal_id} não encontrado.")
            return

        mensagens = CANAIS[canal_id]["mensagens"]
        mensagem = random.choice(mensagens)
        await canal.send(mensagem)

    # ── Comandos de administração ───────────────────────────────────────
    @app_commands.command(name="autopilot_toggle", description="[Staff] Liga ou desliga as mensagens automáticas do bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_toggle(self, interaction: discord.Interaction):
        config = ler_config()
        config["ativo"] = not config.get("ativo", True)
        salvar_config(config)

        estado = "🟢 ativado" if config["ativo"] else "🔴 desativado"
        await interaction.response.send_message(f"Autopilot {estado}.", ephemeral=True)

    @app_commands.command(name="autopilot_testar", description="[Staff] Força o envio de uma mensagem automática agora, pra testar.")
    @app_commands.describe(canal="Qual dos dois canais do autopilot testar")
    @app_commands.choices(canal=[
        app_commands.Choice(name="Curiosidades gerais", value="geral"),
        app_commands.Choice(name="Curiosidades de Rocket League", value="rl"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_testar(self, interaction: discord.Interaction, canal: app_commands.Choice[str]):
        canal_id = CANAL_GERAL_ID if canal.value == "geral" else CANAL_RL_ID

        await self._enviar_mensagem(canal_id)

        config = ler_config()
        canais_cfg = config.setdefault("canais", {})
        estado = canais_cfg.setdefault(str(canal_id), {})
        self._agendar_proximo(canal_id, estado)
        salvar_config(config)

        await interaction.response.send_message("✅ Mensagem de teste enviada!", ephemeral=True)

    @autopilot_toggle.error
    async def autopilot_toggle_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar esse comando.", ephemeral=True
            )

    @autopilot_testar.error
    async def autopilot_testar_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar esse comando.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Autopilot(bot))
