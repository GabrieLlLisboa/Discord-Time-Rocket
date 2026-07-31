import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
import time
from datetime import datetime, timezone, timedelta
from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Autopilot
#  Arquivo: cogs/autopilot.py
#  O bot manda mensagens automáticas sozinho, de tempos em tempos, tudo no
#  mesmo canal, alternando entre dois tipos de conteúdo independentes:
#   - "geral"         -> curiosidades aleatórias (assuntos gerais)
#   - "rocket_league" -> curiosidades de Rocket League
#  Cada tipo tem seu próprio agendamento (sorteado dentro do intervalo dele).
#
#  Regras extras:
#   - O autopilot fica pausado das 22:00 às 12:00 (horário de Brasília).
#   - Se tiver gente conversando no canal (mensagem humana recente), o bot
#     não corta o papo — ele espera a conversa esfriar e checa de novo.
# ─────────────────────────────────────────────

CONFIG_PATH = "data/autopilot.json"

# Fuso horário de Brasília (fixo, o Brasil não usa mais horário de verão).
BR_TZ = timezone(timedelta(hours=-3))

# Janela em que o autopilot fica pausado (não manda nada nesse intervalo).
PAUSA_INICIO_HORA = 22  # a partir das 22:00
PAUSA_FIM_HORA = 12     # até as 12:00 do dia seguinte

# Se alguém mandou mensagem no canal há menos tempo que isso, o bot segura
# o envio automático pra não cortar a conversa. Ele vai checando de novo a
# cada minuto até a conversa esfriar.
ESPERA_CONVERSA_SEGUNDOS = 5 * 60  # 5 minutos

# Canal único onde tudo é enviado (curiosidades gerais e de Rocket League).
CANAL_ID = 1511898323840405655

# Tipo "rocket_league" — intervalo de 2 a 3 horas.
INTERVALO_RL_MIN = 120
INTERVALO_RL_MAX = 180

# Tipo "geral" — intervalo de 3 a 4 horas.
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
    "🚗 Você sabia? Cada carro no jogo pertence a uma categoria de hitbox (Octane, Dominus, Plank, Breakout, Hybrid, Merlin), o que muda como as colisões acontecem, mesmo com carrocerias diferentes.",
    "🕹️ Curiosidade: o Octane é, disparado, o carro mais usado no jogo desde o lançamento, tanto no competitivo quanto no casual.",
    "🏀 Você sabia? Rocket League tem outros modos além do futebol: Hoops (basquete), Snow Day (hóquei), Dropshot (quebrar o chão) e Rumble (com power-ups malucos).",
    "🌀 Curiosidade: o 'half-flip' é uma das primeiras mecânicas avançadas que jogadores aprendem pra virar o carro rapidamente sem perder tempo.",
    "🎯 Você sabia? O 'musty flip' é um flip estiloso que vira o carro no ar antes de tocar a bola — mais pra estilo do que efetividade.",
    "🔁 Curiosidade: o 'flip reset' permite recarregar o flip do carro no ar, tocando a bola de um jeito específico — considerada uma das mecânicas mais difíceis do jogo.",
    "🌐 Você sabia? Rocket League foi um dos primeiros grandes jogos a ter crossplay completo entre PlayStation, Xbox, Nintendo Switch e PC.",
    "🛠️ Curiosidade: existe um modo 'Workshop' feito pela comunidade que permite criar mapas e minigames totalmente customizados dentro do jogo.",
    "🥊 Você sabia? O modo Rumble dá power-ups temporários como congelar a bola, soco, gancho e até tornado.",
    "🏒 Curiosidade: no modo Snow Day, a bola vira um disco de hóquei que desliza diferente da bola tradicional.",
    "🕳️ Você sabia? No Dropshot não existem paredes nem teto — o objetivo é quebrar o chão do time adversário até a bola cair.",
    "🎮 Curiosidade: Rocket League roda a 60 quadros por segundo em consoles desde o lançamento, o que ajudou muito na precisão dos movimentos.",
    "🏟️ Você sabia? O mapa DFH Stadium foi um dos primeiros do jogo e ainda é usado até hoje no competitivo.",
    "🌙 Curiosidade: existe uma variação noturna de vários mapas (como o 'Neon Fields' e o 'Beckwith Park (Stormy)'), com clima e iluminação diferentes.",
    "🏆 Você sabia? O sistema de ranks vai de Bronze até Supersonic Legend (SSL), o topo absoluto do jogo.",
    "📊 Curiosidade: o MMR (rating oculto) de cada jogador é calculado separadamente pra cada modo de jogo (1v1, 2v2, 3v3, etc).",
    "🎨 Curiosidade: existem itens puramente cosméticos no jogo, como rodas, decalques, capacetes e efeitos de boost, que não afetam a jogabilidade.",
    "💥 Você sabia? Bater de frente em outro carro em alta velocidade pode 'demolir' ele, mandando o adversário de volta pro espawn.",
    "🛞 Curiosidade: dá pra trocar as rodas, o boost, a esteira e até o som do motor do seu carro só na parte cosmética.",
    "🎵 Você sabia? Rocket League tem rádios licenciadas dentro do jogo, com playlists de música eletrônica de artistas reais.",
    "🏁 Curiosidade: o modo 'Extra Modes' inclui variações loucas como Ghost Hunt e Spike Rush, criadas em eventos especiais.",
    "🧊 Você sabia? O boost amarelo dá um impulso reto pra frente, mas jogadores avançados usam ele em diagonal pra criar ângulos de aéreo.",
    "🏹 Curiosidade: o 'air dribble' é a técnica de carregar a bola no ar usando pequenos toques, sem deixá-la cair no chão.",
    "🥅 Você sabia? Existem eventos sazonais no jogo, como o de Halloween e Natal, com mapas e itens temáticos temporários.",
    "🎬 Curiosidade: Rocket League ganhou um modo replay completo, onde dá pra assistir e até filmar os melhores momentos da partida com câmera livre.",
    "🏎️ Você sabia? Existem carros licenciados de outras franquias no jogo, como o Batmobile, o DeLorean de 'De Volta Para o Futuro' e carros da Fast & Furious.",
    "🧠 Curiosidade: o tempo de reação médio dos pros em situações de 50/50 (disputa de bola) é considerado um dos fatores que mais separam nível amador de profissional.",
    "🌪️ Você sabia? O power-up de tornado no modo Rumble consegue sugar a bola inteira pro seu lado do campo.",
    "🎯 Curiosidade: o 'ceiling shot' é considerado uma mecânica de nível avançado — usa o teto do mapa pra ganhar impulso antes de finalizar.",
    "🕰️ Você sabia? Uma partida padrão de Rocket League dura 5 minutos, mas pode ir pra prorrogação (overtime) se empatar.",
    "🥇 Curiosidade: a prorrogação em Rocket League é 'morte súbita' — quem fizer o próximo gol vence, não importa quanto tempo passe.",
    "🎮 Você sabia? O jogo já teve edições físicas em disco em consoles, mesmo sendo um jogo majoritariamente digital.",
    "🏆 Curiosidade: o RLCS distribui prêmios em dinheiro em cada temporada, com o Mundial sendo o evento de maior prêmio do ano.",
    "🌍 Você sabia? As regiões competitivas oficiais do RLCS incluem América do Norte, Europa, Oceania, América do Sul, Oriente Médio/Norte da África e Ásia.",
    "🎓 Curiosidade: muitos jogadores profissionais de Rocket League vieram de outros jogos, como FIFA e futebol de campo, antes de migrar pro competitivo.",
    "🔧 Você sabia? A física do carro no jogo é baseada em um motor físico próprio, ajustado especialmente pra dar sensação de peso realista mesmo com movimentos aéreos malucos.",
    "🏅 Curiosidade: além do RLCS, existem torneios amadores e regionais organizados pela própria comunidade, com premiações menores mas competitividade alta.",
    "🎥 Você sabia? Muitos jogadores profissionais fazem streaming ao vivo enquanto treinam, o que ajudou bastante a popularizar mecânicas avançadas.",
    "🧩 Curiosidade: o modo de treino customizado (custom training) permite criar e compartilhar packs de treino específicos pra qualquer mecânica do jogo.",
    "🚦 Você sabia? Existe um sistema de fila de 'casual' separado do 'competitivo', sem afetar o rank do jogador.",
    "🎯 Curiosidade: 'Whiff' é o termo usado quando o jogador erra completamente o toque na bola — motivo de trollagem clássica entre jogadores.",
    "🛡️ Você sabia? Defender bem em Rocket League muitas vezes é mais valorizado entre os pros do que simplesmente atacar sem parar.",
    "🎡 Curiosidade: o modo 'Heatseeker' faz a bola ser atraída automaticamente pro gol mais próximo depois de qualquer toque.",
    "🏗️ Você sabia? Vários mapas do jogo têm variações estruturais, como corners diferentes, o que muda como a bola quica nas quinas.",
    "🎼 Curiosidade: cada torcida virtual do estádio reage com sons diferentes dependendo se o time está ganhando, perdendo ou empatando.",
    "🥁 Você sabia? O jogo tem cross-progression, ou seja, seu progresso e itens acompanham sua conta em qualquer plataforma que você jogar.",
    "🏹 Curiosidade: o 'double tap' é a mecânica de tocar a bola duas vezes rapidamente pra enganar o goleiro, geralmente vindo da trave.",
    "🎮 Você sabia? Rocket League oferece suporte a controle e teclado ao mesmo tempo dentro da mesma partida, sem desvantagem oficial entre eles.",
    "🏆 Curiosidade: o primeiro Mundial oficial de Rocket League aconteceu em 2016, ainda nos primeiros anos do jogo.",
    "🎊 Você sabia? A comunidade de Rocket League é conhecida por ser uma das mais ativas em criar conteúdo de tutorial de mecânicas no YouTube.",
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
    "🌕 Você sabia? A Lua está se afastando da Terra a cerca de 3,8 cm por ano.",
    "🦷 Curiosidade: o esmalte dos dentes é a substância mais dura do corpo humano, mais dura até que o osso.",
    "🐘 Você sabia? Elefantes são um dos poucos animais capazes de se reconhecer em um espelho.",
    "🌊 Curiosidade: mais de 80% dos oceanos do mundo ainda não foram explorados ou mapeados pelo ser humano.",
    "🦋 Você sabia? Borboletas sentem o gosto da comida com os pés.",
    "🧊 Curiosidade: a água quente pode congelar mais rápido que a fria em certas condições — fenômeno conhecido como efeito Mpemba.",
    "🐦 Você sabia? Os beija-flores são as únicas aves capazes de voar de costas.",
    "🌡️ Curiosidade: o corpo humano perde mais calor pela cabeça só porque ela costuma ficar mais exposta, não porque perde proporcionalmente mais que outras partes.",
    "🐨 Você sabia? Os coalas dormem entre 18 e 22 horas por dia.",
    "🌌 Curiosidade: a Via Láctea tem mais de 100 bilhões de estrelas, e o Sol é só uma delas.",
    "🐍 Você sabia? Algumas cobras conseguem 'enxergar' o calor de outros animais através de órgãos sensores especiais.",
    "🍫 Curiosidade: o chocolate branco tecnicamente não é chocolate de verdade, já que não contém sólidos de cacau, só manteiga de cacau.",
    "🦭 Você sabia? Focas conseguem dormir tanto na água quanto na terra, e até com metade do cérebro acordado.",
    "🌋 Curiosidade: existem vulcões ativos até debaixo da água, chamados de vulcões submarinos.",
    "🐜 Você sabia? As formigas não têm pulmões — elas respiram por pequenos poros espalhados pelo corpo.",
    "🌙 Curiosidade: sempre vemos o mesmo lado da Lua da Terra, porque ela gira em sincronia com sua órbita ao redor do nosso planeta.",
    "🐬 Você sabia? Os golfinhos têm nomes próprios — cada um usa um assobio único que os outros reconhecem.",
    "🍅 Curiosidade: o tomate é, botanicamente, uma fruta, mas é tratado como vegetal na culinária.",
    "🦉 Você sabia? Corujas conseguem girar a cabeça até 270 graus, mas não fazem um giro completo de 360.",
    "🌎 Curiosidade: o Monte Everest não é a montanha mais alta desde a base até o topo — esse título é do Mauna Kea, no Havaí, que fica em boa parte submerso.",
    "🐢 Você sabia? Algumas espécies de tartaruga conseguem viver mais de 100 anos.",
    "🌪️ Curiosidade: furacão, tufão e ciclone são o mesmo fenômeno meteorológico, só que com nomes diferentes dependendo da região do mundo.",
    "🐦‍⬛ Você sabia? Corvos conseguem lembrar de rostos humanos por anos e até avisar outros corvos sobre pessoas que consideram uma ameaça.",
    "🍯 Curiosidade: as abelhas precisam visitar cerca de 2 milhões de flores pra produzir apenas 500g de mel.",
    "🧬 Você sabia? Humanos compartilham cerca de 60% do DNA com bananas.",
    "🌡️ Curiosidade: a temperatura mais baixa já registrada na Terra foi de quase -90°C, na Antártida.",
    "🐆 Você sabia? A chita é o animal terrestre mais rápido do mundo, podendo chegar a mais de 100 km/h em curtas distâncias.",
    "🦑 Curiosidade: existem lulas gigantes com olhos do tamanho de uma bola de basquete.",
    "🌍 Você sabia? A Terra não é uma esfera perfeita — ela é levemente achatada nos polos por causa da rotação.",
    "🐋 Curiosidade: o coração de uma baleia-azul é do tamanho de um carro pequeno.",
    "🧠 Você sabia? O cérebro humano não sente dor diretamente, mesmo sendo o órgão responsável por processar toda a sensação de dor do corpo.",
    "🐿️ Curiosidade: esquilos plantam sem querer milhares de árvores todo ano, só por esquecerem onde enterraram suas sementes.",
    "🌈 Você sabia? Um arco-íris duplo acontece quando a luz é refletida duas vezes dentro das gotas de chuva.",
    "🐊 Curiosidade: jacarés não conseguem colocar a língua pra fora, porque ela é presa ao céu da boca.",
    "🌕 Você sabia? Astronautas ficam alguns centímetros mais altos no espaço, porque a falta de gravidade descomprime a coluna.",
    "🐝 Curiosidade: zangões conseguem voar mesmo tendo asas proporcionalmente pequenas pro tamanho do corpo, algo que intrigou cientistas por anos.",
    "🦥 Você sabia? Preguiças descem da árvore só uma vez por semana, geralmente pra fazer suas necessidades.",
    "🌊 Curiosidade: as ondas do oceano podem viajar milhares de quilômetros antes de finalmente quebrar na praia.",
    "🐐 Você sabia? As pupilas das cabras são horizontais, o que ajuda a ter um campo de visão bem mais amplo.",
    "🧊 Curiosidade: o gelo é menos denso que a água líquida, por isso ele flutua em vez de afundar.",
    "🐦 Você sabia? Os flamingos nascem com penas cinzas — a cor rosa vem da alimentação rica em crustáceos e algas.",
    "🌑 Curiosidade: eclipses solares só acontecem durante a lua nova, mas nem toda lua nova gera um eclipse.",
    "🦔 Você sabia? Ouriços conseguem se enrolar formando uma bola quase perfeita como forma de defesa.",
    "🍄 Curiosidade: os cogumelos são mais próximos geneticamente dos animais do que das plantas.",
    "🐻 Você sabia? Ursos polares têm a pele preta por baixo da pelagem branca, o que ajuda a absorver mais calor do sol.",
    "🌡️ Curiosidade: 0°C e 32°F representam exatamente a mesma temperatura, só em escalas diferentes.",
    "🐙 Você sabia? Polvos conseguem mudar de cor e textura da pele em frações de segundo pra se camuflar.",
    "🌎 Curiosidade: mais pessoas vivem dentro do círculo formado ao redor da Ásia do que fora dele, em todo o resto do mundo.",
    "🐺 Você sabia? Lobos uivam pra se comunicar à distância com o resto da matilha, não só pra 'chamar a lua'.",
    "🍇 Curiosidade: existem uvas que soltam pequenas faíscas quando cortadas ao meio e colocadas no micro-ondas, por causa da concentração de água e minerais.",
    "🦩 Você sabia? Flamingos conseguem dormir em pé, apoiados em uma perna só, sem gastar quase energia nenhuma pra isso.",
    "🌌 Curiosidade: a luz do Sol demora cerca de 8 minutos pra chegar até a Terra.",
    "🐍 Você sabia? Cobras não têm pálpebras — por isso parecem estar sempre olhando fixamente.",
    "🍌 Curiosidade: bananas são levemente radioativas, por causa do potássio presente na fruta, mas em nível completamente inofensivo.",
    "🦈 Você sabia? Tubarões precisam ficar se movendo constantemente, senão algumas espécies afundam ou não conseguem respirar direito.",
    "🌧️ Curiosidade: em Veneza, na Itália, algumas ruas literalmente são canais — os moradores usam barco no lugar de carro no dia a dia.",
    "🐢 Você sabia? O sexo de algumas tartarugas é definido pela temperatura do ninho durante a incubação dos ovos.",
    "🧫 Curiosidade: existem mais bactérias vivendo no seu corpo do que células humanas, segundo estimativas científicas atuais.",
    "🦅 Você sabia? Águias conseguem enxergar detalhes de uma presa a quilômetros de distância, com uma visão muito mais aguçada que a humana.",
    "🌋 Curiosidade: o supervulcão sob o Parque Yellowstone, nos EUA, é monitorado 24 horas por dia por cientistas.",
    "🐌 Você sabia? Caracóis têm milhares de dentinhos minúsculos organizados em fileiras dentro da boca.",
    "🌊 Curiosidade: a Fossa das Marianas é o ponto mais profundo já registrado nos oceanos, com quase 11 km de profundidade.",
    "🐦 Você sabia? Papagaios conseguem imitar não só palavras, mas até o tom de voz de quem os ensinou.",
    "🍋 Curiosidade: o limão tem mais açúcar do que o morango, mas o ácido cítrico disfarça o sabor doce.",
    "🐧 Você sabia? Pinguins-macho, em algumas espécies, oferecem uma pedrinha bonita pra 'conquistar' a fêmea.",
    "🌡️ Curiosidade: o metal mais condutor de eletricidade que existe naturalmente é a prata.",
    "🐺 Você sabia? Cães conseguem farejar mudanças emocionais nos humanos através do cheiro do suor e da respiração.",
    "🌕 Curiosidade: a Lua não tem luz própria — o brilho que vemos é só reflexo da luz do Sol.",
    "🦒 Você sabia? Girafas dormem em média só cerca de 2 horas por dia, em pequenos cochilos.",
    "🐳 Curiosidade: baleias jubarte cantam músicas complexas que podem durar até 30 minutos e se repetir em padrão.",
    "🌎 Você sabia? A Rússia tem 11 fusos horários diferentes, mais que qualquer outro país do mundo.",
    "🐝 Curiosidade: abelhas conseguem se comunicar através de uma 'dança' que indica a direção e distância de flores com néctar.",
    "🦁 Você sabia? Um rugido de leão pode ser ouvido a até 8 km de distância em condições ideais.",
    "🌡️ Curiosidade: o corpo humano tem cerca de 37°C de temperatura média, mas isso varia um pouco ao longo do dia.",
    "🐿️ Você sabia? Esquilos-voadores não voam de verdade — eles planam usando uma membrana de pele entre as patas.",
    "🍓 Curiosidade: cada morango tem, em média, cerca de 200 sementinhas na superfície.",
    "🐊 Você sabia? Crocodilos existem há mais de 200 milhões de anos, sobrevivendo até à extinção dos dinossauros.",
    "🌙 Curiosidade: a Lua é a responsável direta pelas marés dos oceanos, por causa da atração gravitacional.",
    "🐦‍🔥 Você sabia? Existem aves, como o flamingo-chileno, que migram voando em bando por milhares de quilômetros todos os anos.",
    "🍯 Curiosidade: o mel de algumas regiões pode ter cor, sabor e até textura diferentes dependendo das flores que as abelhas visitaram.",
    "🐨 Você sabia? Coalas têm impressões digitais tão parecidas com as humanas que já confundiram investigações forenses.",
    "🌊 Curiosidade: ondas gigantes chamadas de 'tsunamis' podem viajar pelo oceano na velocidade de um avião comercial.",
    "🐍 Você sabia? A jararaca e outras cobras peçonhentas usam o veneno principalmente pra caçar, não como primeira defesa.",
    "🌌 Curiosidade: se o Sol fosse do tamanho de uma bola de basquete, a Terra seria do tamanho de uma cabeça de alfinete, numa escala real.",
    "🦔 Você sabia? Ouriços são imunes a boa parte dos venenos de cobra, o que ajuda na hora de se defenderem.",
    "🍄 Curiosidade: existe um fungo gigante em Oregon, nos EUA, considerado um dos maiores organismos vivos do planeta, cobrindo vários quilômetros quadrados.",
    "🐋 Você sabia? Cachalotes conseguem mergulhar por mais de uma hora sem precisar respirar.",
    "🌡️ Curiosidade: o ponto de ebulição da água muda de acordo com a altitude — por isso comida demora mais pra cozinhar em lugares muito altos.",
    "🐦 Você sabia? O beija-flor bate as asas até 80 vezes por segundo, dependendo da espécie.",
    "🍫 Curiosidade: o cacau já foi usado como moeda de troca por civilizações antigas da América Central.",
    "🐢 Você sabia? A tartaruga-das-galápagos é uma das espécies de tartaruga terrestre mais longevas conhecidas.",
    "🌎 Curiosidade: o Canadá tem mais lagos do que todos os outros países do mundo somados.",
    "🐘 Você sabia? Elefantes se comunicam por infrassom, sons tão graves que o ouvido humano não consegue captar.",
    "🌡️ Curiosidade: o vidro é tecnicamente considerado um líquido super resfriado por alguns cientistas, embora se comporte como sólido no dia a dia.",
    "🐦 Você sabia? Existem pinguins que vivem em regiões quentes, como o pinguim-de-galápagos, perto da linha do Equador.",
    "🌊 Curiosidade: mais de 90% de todas as espécies que já existiram na Terra estão extintas hoje.",
    "🐝 Você sabia? Uma colmeia pode ter dezenas de milhares de abelhas trabalhando de forma extremamente organizada.",
]

# ── Enquetes rápidas (terceiro tipo de mensagem) ────────────────────────────
# Em vez de só mandar uma curiosidade pra leitura passiva, de vez em quando o
# bot manda uma enquete com reações, pra gerar interação de verdade.
# Chance de qualquer envio ser uma enquete em vez de curiosidade.
CHANCE_ENQUETE = 0.2

ENQUETES_RL = [
    {"pergunta": "Qual seu rank atual?", "opcoes": [("🥉", "Bronze / Prata"), ("🥈", "Ouro / Platina"), ("💎", "Diamante / Champion"), ("🏆", "GC ou acima")]},
    {"pergunta": "Qual sua posição favorita?", "opcoes": [("🛡️", "Defesa"), ("⚙️", "Meio"), ("⚔️", "Ataque")]},
    {"pergunta": "Qual carro você mais usa?", "opcoes": [("🚗", "Octane"), ("🏎️", "Dominus"), ("🚙", "Fennec"), ("🛻", "Outro")]},
    {"pergunta": "Qual modo você prefere jogar?", "opcoes": [("⚽", "Padrão (Soccer)"), ("🏀", "Hoops"), ("🏒", "Snow Day"), ("🕳️", "Dropshot")]},
    {"pergunta": "1v1, 2v2 ou 3v3?", "opcoes": [("1️⃣", "1v1"), ("2️⃣", "2v2"), ("3️⃣", "3v3")]},
    {"pergunta": "Qual mecânica você mais quer aprender?", "opcoes": [("🌀", "Flip reset"), ("🎯", "Air dribble"), ("🔺", "Ceiling shot"), ("↩️", "Half-flip")]},
    {"pergunta": "Você joga mais no controle ou teclado?", "opcoes": [("🎮", "Controle"), ("⌨️", "Teclado/Mouse")]},
    {"pergunta": "Qual time você torce no RLCS?", "opcoes": [("🌎", "Time das Américas"), ("🌍", "Time da Europa"), ("🌏", "Time da Ásia/Oceania"), ("🤷", "Não acompanho")]},
]

ENQUETES_GERAIS = [
    {"pergunta": "Doce ou salgado?", "opcoes": [("🍫", "Doce"), ("🧂", "Salgado")]},
    {"pergunta": "Praia ou montanha?", "opcoes": [("🏖️", "Praia"), ("⛰️", "Montanha")]},
    {"pergunta": "Café ou energético?", "opcoes": [("☕", "Café"), ("⚡", "Energético")]},
    {"pergunta": "Prefere calor ou frio?", "opcoes": [("🔥", "Calor"), ("❄️", "Frio")]},
    {"pergunta": "Voar ou ficar invisível?", "opcoes": [("🕊️", "Voar"), ("👻", "Invisível")]},
    {"pergunta": "Filme ou série?", "opcoes": [("🎬", "Filme"), ("📺", "Série")]},
    {"pergunta": "Você é mais dia ou noite?", "opcoes": [("☀️", "Dia"), ("🌙", "Noite")]},
    {"pergunta": "Pizza com ou sem borda recheada?", "opcoes": [("🧀", "Com borda"), ("🍕", "Sem borda")]},
]

# Configuração de cada tipo de mensagem do autopilot.
# Os dois tipos mandam mensagem no mesmo canal (CANAL_ID), cada um com seu
# próprio agendamento independente.
CANAIS = {
    "geral": {"nome": "geral", "canal_id": CANAL_ID, "mensagens": CURIOSIDADES_GERAIS, "enquetes": ENQUETES_GERAIS, "intervalo_min": INTERVALO_GERAL_MIN, "intervalo_max": INTERVALO_GERAL_MAX},
    "rocket_league": {"nome": "rocket_league", "canal_id": CANAL_ID, "mensagens": CURIOSIDADES_RL, "enquetes": ENQUETES_RL, "intervalo_min": INTERVALO_RL_MIN, "intervalo_max": INTERVALO_RL_MAX},
}


def ler_config() -> dict:
    """Estrutura salva em disco:
    {
      "ativo": True,
      "canais": {
         "geral": {"proximo_envio_ts": 123456.0},
         "rocket_league": {"proximo_envio_ts": 123456.0}
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

        if self._em_pausa():
            # Dentro da janela 22:00–12:00 (horário de Brasília): não manda
            # nada. Os agendamentos continuam parados até a janela acabar.
            return

        canais_cfg = config.setdefault("canais", {})
        agora = time.time()
        precisa_salvar = False

        for chave in CANAIS:
            estado = canais_cfg.setdefault(chave, {})
            proximo_ts = estado.get("proximo_envio_ts")

            if not proximo_ts:
                # Primeira vez rodando pra esse tipo — agenda e segue.
                self._agendar_proximo(chave, estado)
                precisa_salvar = True
                continue

            if agora >= proximo_ts:
                if await self._conversa_recente(chave):
                    # Tem gente conversando no canal — não corta o papo.
                    # Espera um pouco e checa de novo no próximo minuto.
                    estado["proximo_envio_ts"] = agora + 60
                    precisa_salvar = True
                    continue

                try:
                    await self._enviar_mensagem(chave)
                except Exception as e:
                    # Uma falha pontual (canal deletado, sem permissão, etc.)
                    # não pode derrubar o loop pro resto da vida do processo.
                    print(f"[AUTOPILOT] ⚠️ Erro ao enviar mensagem do tipo {chave}: {e}")
                finally:
                    self._agendar_proximo(chave, estado)
                    precisa_salvar = True

        if precisa_salvar:
            salvar_config(config)

    def _em_pausa(self) -> bool:
        """True se agora estiver dentro da janela de pausa do autopilot
        (22:00 até 12:00 do dia seguinte, horário de Brasília)."""
        hora_atual = datetime.now(BR_TZ).hour
        return hora_atual >= PAUSA_INICIO_HORA or hora_atual < PAUSA_FIM_HORA

    async def _conversa_recente(self, chave: str) -> bool:
        """True se a última mensagem humana no canal foi recente demais pra
        o bot interromper com uma mensagem automática."""
        cfg_canal = CANAIS[chave]
        canal = self.bot.get_channel(cfg_canal["canal_id"])
        if canal is None:
            return False

        try:
            async for msg in canal.history(limit=5):
                if msg.author.bot:
                    continue
                idade_segundos = (datetime.now(timezone.utc) - msg.created_at).total_seconds()
                return idade_segundos < ESPERA_CONVERSA_SEGUNDOS
        except (discord.Forbidden, discord.HTTPException):
            return False

        return False

    def _agendar_proximo(self, chave: str, estado: dict) -> None:
        """Sorteia o intervalo (específico de cada tipo) até a próxima
        mensagem e salva o timestamp absoluto, pra sobreviver a reinícios
        do bot."""
        cfg_canal = CANAIS[chave]
        intervalo_minutos = random.randint(cfg_canal["intervalo_min"], cfg_canal["intervalo_max"])
        estado["proximo_envio_ts"] = time.time() + (intervalo_minutos * 60)

    @autopilot_loop.before_loop
    async def before_autopilot_loop(self):
        await self.bot.wait_until_ready()
        config = ler_config()
        canais_cfg = config.setdefault("canais", {})
        mudou = False
        for chave in CANAIS:
            estado = canais_cfg.setdefault(chave, {})
            if not estado.get("proximo_envio_ts"):
                self._agendar_proximo(chave, estado)
                mudou = True
        if mudou:
            salvar_config(config)

    async def _enviar_mensagem(self, chave: str):
        cfg_canal = CANAIS[chave]
        canal = self.bot.get_channel(cfg_canal["canal_id"])
        if canal is None:
            print(f"[AUTOPILOT] ⚠️ Canal {cfg_canal['canal_id']} não encontrado.")
            return

        enquetes = cfg_canal.get("enquetes")

        if enquetes and random.random() < CHANCE_ENQUETE:
            await self._enviar_enquete(canal, random.choice(enquetes))
            return

        mensagem = random.choice(cfg_canal["mensagens"])
        await canal.send(mensagem)

    async def _enviar_enquete(self, canal: discord.abc.Messageable, enquete: dict):
        opcoes_texto = "\n".join(f"{emoji}  {texto}" for emoji, texto in enquete["opcoes"])
        embed = discord.Embed(
            title="📊 Enquete rápida!",
            description=f"**{enquete['pergunta']}**\n\n{opcoes_texto}",
            color=0xEB459E,
        )
        embed.set_footer(text="Reage aí com um dos emojis pra votar!")

        try:
            msg = await canal.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[AUTOPILOT] ⚠️ Erro ao enviar enquete: {e}")
            return

        for emoji, _ in enquete["opcoes"]:
            try:
                await msg.add_reaction(emoji)
            except discord.HTTPException:
                pass

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
    @app_commands.describe(canal="Qual dos dois tipos de mensagem do autopilot testar")
    @app_commands.choices(canal=[
        app_commands.Choice(name="Curiosidades gerais", value="geral"),
        app_commands.Choice(name="Curiosidades de Rocket League", value="rl"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def autopilot_testar(self, interaction: discord.Interaction, canal: app_commands.Choice[str]):
        chave = "geral" if canal.value == "geral" else "rocket_league"

        await self._enviar_mensagem(chave)

        config = ler_config()
        canais_cfg = config.setdefault("canais", {})
        estado = canais_cfg.setdefault(chave, {})
        self._agendar_proximo(chave, estado)
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
