import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
import time
from datetime import datetime, timezone, timedelta

from cogs.json_store import ler_json, salvar_json
import cogs.atividade as atividade_mod

# ─────────────────────────────────────────────
#  Cog: Autopilot
#  Arquivo: cogs/autopilot.py
#  O bot manda mensagens sozinho de tempos em tempos:
#  incentivo, brincadeiras/interação e curiosidades de RL.
# ─────────────────────────────────────────────

CONFIG_PATH = "data/autopilot.json"

# Canal padrão: chat geral (pode ser sobrescrito por /autopilot_canal ou pelo .env)
CANAL_PADRAO_ID = int(os.getenv("AUTOPILOT_CHANNEL_ID", 1529233653052346398))

# Intervalo (minutos) entre uma mensagem e outra — sorteado dentro dessa faixa
# pra não ficar previsível / robótico.
INTERVALO_MIN = int(os.getenv("AUTOPILOT_INTERVALO_MIN", 30))
INTERVALO_MAX = int(os.getenv("AUTOPILOT_INTERVALO_MAX", 40))


def ler_config() -> dict:
    return ler_json(CONFIG_PATH, {
        "ativo": True,
        "canal_id": CANAL_PADRAO_ID or None,
        "ultima_categoria": None,
        "proximo_envio_ts": None,
    })


def salvar_config(dados: dict) -> None:
    salvar_json(CONFIG_PATH, dados)


# ── Conteúdo ─────────────────────────────────────────────────────────────────
INCENTIVO = [
    "💪 Bora treinar hoje? Todo Grand Champion um dia já foi Bronze também.",
    "🔥 Lembrete do dia: aim ruim se treina, rotação ruim se treina, atitude ruim... também dá pra treinar 😏",
    "🔥 Depois de um dia difícil de rank, lembra: até o Squishy já teve dia ruim de mira.",
    "🏆 Cada partida é uma chance de aprender algo novo. Bora pra treinos hoje?",
    "⚡ Se você perdeu uma partida hoje, isso não te define. Levanta e chama o próximo amistoso!",
    "🎯 Foco no processo, não só no resultado. Boost management ganha mais partida que mecânica bonita.",
    "🥇 Quem treina consistência é quem sobe de elo. Nada de sessão de 8h só uma vez por mês, hein!",
    "🚀 Rank não sobe sozinho: cada treino de hoje é um degrau pro seu próximo elo.",
    "😤 Perdeu de shot no último segundo? Guarda a raiva, chama o próximo amistoso e desconta em campo.",
    "🎮 Aquele mecânico que você treina hoje e erra 10 vezes, semana que vem você acerta sem pensar.",
    "🔥 Não existe jogador ruim, existe jogador que ainda não treinou o suficiente. Bora nessa!",
    "💥 Um dia de treino não muda nada. Um mês de treino muda tudo. Continua!",
    "🏋️ Freeplay 20 minutinhos por dia já faz diferença gigante no seu aim depois de algumas semanas.",
    "🧠 Rank também é mental: descansa a cabeça antes de tiltar a sessão inteira.",
    "🎯 Cada replay que você assiste dos seus próprios jogos te ensina mais que 10 partidas jogando no automático.",
    "⭐ Não compara sua jornada com a dos outros. Compara você hoje com você de 1 mês atrás.",
    "🥊 Time que se comunica sobe junto. Chama o call e treina rotação com a galera!",
    "🚧 Travou de rank? É sinal que chegou a hora de mudar o treino, não de desistir.",
    "🏆 Quem não erra flip reset é porque não tenta. Continua tentando, o resultado vem.",
    "💡 Assistir replay de pro player ensina mais posicionamento do que qualquer dica de chat.",
    "🔋 Boost mal usado é rank perdido. Treina economia de boost hoje, é de graça e muda o jogo.",
]

BRINCADEIRAS = [
    "🎮 Pergunta rápida: qual foi o gol mais bonito que você já fez no RL? Conta aqui embaixo! 👇",
    "😂 Se seu carro fosse um dos seus companheiros de time, qual seria e por quê? Marca ele aqui!",
    "🤔 Enquete relâmpago: você prefere ser o rotação (defesa) ou o finalizador (ataque) do time?",
    "🏁 Quem topa um 1v1 ou 2v2 agora? Reage aqui com 🎮 se tiver on!",
    "😅 Confessa: quantas vezes você já tentou um flip reset e caiu tipo saco de batata?",
    "🔥 Vamos ver quem se garante: manda um print do seu melhor placar da semana aqui no chat!",
    "🎲 Curiosidade: alguém aqui já resetou o PC de raiva depois de perder de shot no último segundo? 😂",
]

CURIOSIDADES = [
    "📚 Você sabia? O Rocket League foi lançado em 2015 e é sucessor espiritual do jogo 'Supersonic Acrobatic Rocket-Powered Battle-Cars'.",
    "📚 Curiosidade: o boost total do carro dura cerca de 10 segundos de uso contínuo em linha reta.",
    "📚 Você sabia? Os pads de boost pequenos dão 12 de boost e os grandes enchem o tanque (100).",
    "📚 Curiosidade: o Rocket League se tornou free-to-play em setembro de 2020.",
    "📚 Você sabia? O RLCS (Rocket League Championship Series) é a principal liga profissional do jogo desde 2016.",
    "📚 Curiosidade: existem mais de 15 mapas diferentes no modo competitivo padrão ao longo da história do jogo.",
    "📚 Você sabia? Um 'ceiling shot' usa o teto do mapa pra pegar impulso antes de finalizar — é uma das mecânicas mais avançadas.",
    # ── Curiosidade especial do servidor ──
    "🔥 Você sabia que o criador do flip reset está no nosso servidor? É o **fyshokid**! 👀",
    # ── Recordes e histórico de RLCS ──
    "🏆 Curiosidade RLCS: alguns jogadores acumulam anos de campeonato sem nunca terem levantado um troféu mundial — a pressão no cenário competitivo é gigante.",
    "🥇 Curiosidade RLCS: os times europeus dominam boa parte dos títulos mundiais da história da competição.",
    "📈 Você sabia? Vários jogadores profissionais de RLCS começaram a competir ainda na adolescência, alguns com menos de 16 anos.",
    "🌟 Curiosidade: o cenário competitivo de Rocket League tem verdadeiros prodígios que já jogavam em nível profissional antes mesmo de terem carteira de motorista.",
    # ── Perguntas engraçadas / interação ──
    "😂 Pergunta séria: quantos controles você já quebrou de raiva jogando RL? Sê sincero.",
    "🤡 Enquete do caos: o que é pior, tomar gol no último segundo ou perder de whiff feio na frente do gol vazio?",
    "😆 Curiosidade duvidosa: tem gente que jura que o ping influencia mais que o próprio aim. Vocês concordam?",
    # ── Assuntos atuais / aleatórios ──
    "🗞️ Bora comentar: o que vocês acham das mudanças recentes no cenário competitivo de RL?",
    "🎲 Aleatório do dia: se Rocket League ganhasse um mapa novo amanhã, que tema vocês queriam? Espaço, deserto, praia?",
    "🎲 Pergunta sem nexo: se você pudesse trocar seu carro por qualquer carro do jogo, qual escolheria e por quê?",
    "🎲 Curiosidade aleatória: sabia que dá pra jogar Rocket League com o carro andando de ré o jogo inteiro? Ninguém faz isso, mas dá.",
    "📚 Você sabia? O Rocket League roda a 120 quadros por segundo no PC quando o hardware permite, o que ajuda demais na precisão dos inputs.",
    "📚 Curiosidade: o modo Hoops (basquete) e o Dropshot (piso que quebra) são variações oficiais do próprio jogo, não são mods.",
    "🚗 Você sabia? O carro Octane é de longe o mais usado no competitivo por causa do hitbox (a 'caixa' de colisão) considerada mais equilibrada.",
    "🏟️ Curiosidade: o mapa DFH Stadium foi um dos primeiros do jogo e ainda é usado no competitivo até hoje.",
    "🎮 Você sabia? Rocket League já teve crossplay entre PlayStation, Xbox, Switch e PC bem antes de virar padrão em outros jogos.",
    "🥅 Curiosidade: existe um recorde de gol mais rápido de uma partida — feito literalmente nos primeiros segundos do jogo.",
    "🔧 Você sabia? Cada carro tem uma 'hitbox' diferente (Octane, Dominus, Breakout, etc.), mesmo que a aparência visual mude, a física de colisão pode ser igual entre alguns modelos.",
    "🏆 Curiosidade RLCS: já teve final de mundial decidida na prorrogação, com milhões de espectadores assistindo ao vivo.",
    "🌐 Você sabia? Rocket League tem servidores dedicados em várias regiões do mundo, e o matchmaking tenta te colocar sempre no de menor ping.",
    "⚡ Curiosidade: o 'air roll' foi uma das mecânicas que mais mudou o nível competitivo do jogo desde que virou popular.",
    "🎨 Você sabia? Existem itens puramente cosméticos no jogo que já foram revendidos por milhares de dólares no mercado de trocas.",
    "🛞 Curiosidade: as rodas do carro são só estética — elas não influenciam em nada na física ou na velocidade do carro.",
    "📅 Você sabia? O Rocket League completou 10 anos de existência em 2025, um marco gigante pra um jogo de carros com bola.",
    "🤖 Curiosidade: bots do próprio jogo (nível fácil, médio, difícil) são usados até por pro players pra treinar mecânicas específicas.",
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
    "🌕 Você sabia? A Lua está se afastando da Terra cerca de 3,8 cm por ano.",
    "🐙 Curiosidade: polvos conseguem mudar a cor E a textura da pele em menos de 1 segundo pra se camuflar.",
    "🧊 Você sabia? A água quente pode congelar mais rápido que a água fria em certas condições — é o chamado 'efeito Mpemba'.",
    "🦋 Curiosidade: borboletas sentem gosto com as patas, não com a boca.",
    "🌙 Você sabia? Um dia em Vênus é mais longo que um ano em Vênus, porque o planeta gira muito devagar em torno do próprio eixo.",
    "🐘 Curiosidade: elefantes são os únicos mamíferos que não conseguem pular, por causa da estrutura das patas.",
    "🍫 Você sabia? O chocolate branco tecnicamente não é chocolate, porque não contém sólidos de cacau, só manteiga de cacau.",
    "🦷 Curiosidade: o esmalte dos dentes é a substância mais dura do corpo humano, mais até que os ossos.",
    "🌊 Você sabia? Mais de 80% dos oceanos da Terra ainda não foram explorados ou mapeados pelo ser humano.",
    "🐦 Curiosidade: os beija-flores são as únicas aves capazes de voar pra trás.",
    "🧬 Você sabia? Humanos compartilham cerca de 60% do DNA com bananas.",
    "🕷️ Curiosidade: as teias de algumas aranhas são tão resistentes que, proporcionalmente, seriam mais fortes que o aço.",
    "🌡️ Você sabia? O corpo humano perde mais calor pela cabeça só porque ela costuma ficar exposta, não porque tem alguma propriedade especial.",
    "🐢 Curiosidade: algumas espécies de tartaruga conseguem viver mais de 100 anos, e algumas até passam dos 150.",
]

CATEGORIAS = {
    "incentivo": INCENTIVO,
    "brincadeira": BRINCADEIRAS,
    "curiosidade": CURIOSIDADES,
    "curiosidade_geral": CURIOSIDADES_GERAIS,
}

# ── Madrugada: nada de incentivo, só curiosidade/brincadeira ────────────────
# Entre 00h e 06h (horário de Brasília, UTC-3) o bot não manda mensagens de
# incentivo (nem a categoria "incentivo" nem o incentivo direcionado a membro
# inativo) — nesse horário só rola curiosidade/curiosidade_geral/brincadeira.
FUSO_BRASILIA = timezone(timedelta(hours=-3))
MADRUGADA_INICIO = 0   # 00:00
MADRUGADA_FIM = 6      # 06:00 (intervalo [0h, 6h))

CATEGORIAS_BLOQUEADAS_MADRUGADA = {"incentivo"}


def em_madrugada() -> bool:
    hora_atual = datetime.now(FUSO_BRASILIA).hour
    return MADRUGADA_INICIO <= hora_atual < MADRUGADA_FIM

# ── Incentivo direcionado a membros inativos ────────────────────────────────
# 70% das vezes (CHANCE_INCENTIVO_INATIVO), em vez de uma mensagem genérica,
# o bot chama por nome/menção algum membro inativo — com prioridade pra quem
# NUNCA mandou nenhuma mensagem — incentivando a pessoa a participar.
CHANCE_INCENTIVO_INATIVO = 0.7

INCENTIVO_DIRECIONADO = [
    "Ei {mention}, ainda não te vimos por aqui no chat! Bora dar um alô? 👋",
    "{mention} cadê você? O servidor tá esperando sua estreia no chat! 🔥",
    "Psst, {mention}... já pensou em soltar o verbo aqui no chat hoje? Bora! 💬",
    "{mention} tá guardando as palavras pra quê? Vem interagir com a galera! 😄",
    "E aí {mention}, que tal quebrar o silêncio e mandar sua primeira mensagem hoje? 🎮",
    "{mention}, o servidor sente sua falta no chat! Aparece aí! 🙌",
    "Alguém viu o(a) {mention}? Ainda tá devendo aquele 'oi' pro servidor! 👀",
    "{mention}, bora contar pra gente qual seu rank atual? Vem interagir! 🏆",
]


def _membro_ja_falou(dados_atividade: dict, membro: discord.Member) -> bool:
    registro = dados_atividade.get(str(membro.id))
    return bool(registro and registro.get("mensagens", 0) > 0)


def _membro_ja_foi_anunciado(dados_atividade: dict, membro: discord.Member) -> bool:
    registro = dados_atividade.get(str(membro.id))
    return bool(registro and registro.get("anunciado", False))


# Depois de chamar alguém, esse membro fica "de fora" por um tempo — assim o
# incentivo direcionado roda entre todo mundo elegível, em vez de sempre cair
# na mesma pessoa (ex: só tem 1 membro que nunca falou nada, então sem esse
# cooldown ele seria escolhido toda vez).
COOLDOWN_INCENTIVO_MEMBRO_SEG = 3 * 60 * 60  # 3 horas


def _escolher_membro_inativo(guild: discord.Guild) -> discord.Member | None:
    """Escolhe um membro inativo pra incentivar, dando prioridade (mas não
    exclusividade) a quem NUNCA mandou mensagem nenhuma, e evitando repetir
    a mesma pessoa antes do cooldown passar — pra rodar entre todo mundo
    elegível em vez de martelar sempre a mesma."""
    dados_atividade = ler_json(atividade_mod.DATA_PATH, {})
    config = ler_config()
    ultimos_incentivos = config.setdefault("ultimo_incentivo", {})
    agora = time.time()

    candidatos = []
    for membro in guild.members:
        if membro.bot:
            continue
        if atividade_mod.entrou_durante_periodo(membro):
            continue
        if _membro_ja_foi_anunciado(dados_atividade, membro):
            continue  # já bateu a meta de atividade, não precisa de incentivo

        ultimo = ultimos_incentivos.get(str(membro.id), 0)
        if agora - ultimo < COOLDOWN_INCENTIVO_MEMBRO_SEG:
            continue  # foi chamado(a) recentemente, dá espaço pros outros

        candidatos.append(membro)

    if not candidatos:
        return None

    nunca_falaram = [m for m in candidatos if not _membro_ja_falou(dados_atividade, m)]
    # 70% de chance de priorizar quem nunca falou nada (se tiver alguém nessa
    # situação disponível); os outros 30% dão chance pra quem já falou pouco
    # mas segue inativo — evita ficar só em cima de 1 pessoa.
    if nunca_falaram and random.random() < 0.7:
        escolhido = random.choice(nunca_falaram)
    else:
        escolhido = random.choice(candidatos)

    ultimos_incentivos[str(escolhido.id)] = agora
    salvar_config(config)
    return escolhido


def escolher_mensagem(ultima_categoria: str | None) -> tuple[str, str]:
    """Escolhe uma categoria diferente da última (pra não repetir o mesmo tipo
    de mensagem duas vezes seguidas) e sorteia uma mensagem dela.
    Durante a madrugada (0h-6h, horário de Brasília), incentivo fica fora —
    só curiosidade/curiosidade_geral/brincadeira."""
    categorias_base = CATEGORIAS
    if em_madrugada():
        categorias_base = {c: msgs for c, msgs in CATEGORIAS.items() if c not in CATEGORIAS_BLOQUEADAS_MADRUGADA}

    categorias_disponiveis = [c for c in categorias_base if c != ultima_categoria]
    if not categorias_disponiveis:
        categorias_disponiveis = list(categorias_base)

    categoria = random.choice(categorias_disponiveis)
    mensagem = random.choice(categorias_base[categoria])
    return categoria, mensagem


class Autopilot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autopilot_loop.start()

    def cog_unload(self):
        self.autopilot_loop.cancel()

    @tasks.loop(minutes=1)
    async def autopilot_loop(self):
        await self.bot.wait_until_ready()

        # O horário do próximo envio fica salvo em disco (data/autopilot.json),
        # como um timestamp absoluto. Assim, se o bot reiniciar, ele lê esse
        # mesmo horário salvo em vez de sortear um novo — o tempo de espera
        # NÃO é resetado por um restart.
        config = ler_config()
        proximo_ts = config.get("proximo_envio_ts")

        if not proximo_ts:
            # Primeira vez rodando (nunca foi agendado) — sorteia e salva.
            self._agendar_proximo(config)
            return

        if time.time() >= proximo_ts:
            try:
                await self._enviar_mensagem()
            except Exception as e:
                # Uma falha pontual (canal deletado, sem permissão, etc.) não
                # pode derrubar o loop pro resto da vida do processo.
                print(f"[AUTOPILOT] ⚠️ Erro ao enviar mensagem automática: {e}")
            finally:
                config = ler_config()
                self._agendar_proximo(config)

    def _agendar_proximo(self, config: dict) -> None:
        """Sorteia o intervalo até a próxima mensagem e salva o timestamp
        absoluto em disco, pra sobreviver a reinícios do bot."""
        intervalo_minutos = random.randint(INTERVALO_MIN, INTERVALO_MAX)
        config["proximo_envio_ts"] = time.time() + (intervalo_minutos * 60)
        salvar_config(config)

    @autopilot_loop.before_loop
    async def before_autopilot_loop(self):
        await self.bot.wait_until_ready()
        # Se ainda não existe um horário agendado (primeira execução do bot
        # na vida), sorteia um intervalo inicial e salva. Se já existir um
        # horário salvo de antes (bot reiniciado), ele é respeitado — nada é
        # resetado aqui.
        config = ler_config()
        if not config.get("proximo_envio_ts"):
            self._agendar_proximo(config)

    async def _enviar_mensagem(self):
        config = ler_config()

        if not config.get("ativo", True):
            return

        canal_id = config.get("canal_id") or CANAL_PADRAO_ID
        if not canal_id:
            return  # ninguém configurou um canal ainda

        canal = self.bot.get_channel(canal_id)
        if canal is None:
            print(f"[AUTOPILOT] ⚠️ Canal {canal_id} não encontrado.")
            return

        # 70% de chance de chamar especificamente algum membro inativo
        # (com prioridade pra quem nunca mandou mensagem nenhuma). Se não
        # tiver ninguém inativo pra incentivar, cai pro conteúdo normal.
        # Não roda de madrugada — nesse horário é só curiosidade/brincadeira.
        if not em_madrugada() and random.random() < CHANCE_INCENTIVO_INATIVO:
            membro = _escolher_membro_inativo(canal.guild)
            if membro is not None:
                mensagem = random.choice(INCENTIVO_DIRECIONADO).format(mention=membro.mention)
                config["ultima_categoria"] = "incentivo_direcionado"
                salvar_config(config)
                await canal.send(mensagem)
                return

        categoria, mensagem = escolher_mensagem(config.get("ultima_categoria"))
        config["ultima_categoria"] = categoria
        salvar_config(config)

        await canal.send(mensagem)

    # ── Comandos de administração ───────────────────────────────────────
    @app_commands.command(name="autopilot_canal", description="[Staff] Define o canal onde o bot manda mensagens automáticas.")
    @app_commands.describe(canal="Canal que vai receber as mensagens automáticas")
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        config = ler_config()
        config["canal_id"] = canal.id
        salvar_config(config)
        await interaction.response.send_message(
            f"✅ Mensagens automáticas agora serão enviadas em {canal.mention}.", ephemeral=True
        )

    @app_commands.command(name="autopilot_toggle", description="[Staff] Liga ou desliga as mensagens automáticas do bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_toggle(self, interaction: discord.Interaction):
        config = ler_config()
        config["ativo"] = not config.get("ativo", True)
        salvar_config(config)

        estado = "🟢 ativado" if config["ativo"] else "🔴 desativado"
        await interaction.response.send_message(f"Autopilot {estado}.", ephemeral=True)

    @app_commands.command(name="autopilot_testar", description="[Staff] Força o envio de uma mensagem automática agora, pra testar.")
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_testar(self, interaction: discord.Interaction):
        config = ler_config()
        canal_id = config.get("canal_id") or CANAL_PADRAO_ID

        if not canal_id:
            await interaction.response.send_message(
                "⚠️ Nenhum canal configurado ainda. Use `/autopilot_canal` primeiro.", ephemeral=True
            )
            return

        await self._enviar_mensagem()
        self._agendar_proximo(ler_config())
        await interaction.response.send_message("✅ Mensagem de teste enviada!", ephemeral=True)

    @autopilot_canal.error
    async def autopilot_canal_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar esse comando.", ephemeral=True
            )

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
