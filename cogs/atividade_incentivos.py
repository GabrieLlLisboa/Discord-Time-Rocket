"""
Módulo: Mensagens de incentivo aos inativos
Arquivo: cogs/atividade_incentivos.py

32 variações de mensagem que o bot manda no canal de incentivo (ver
atividade.py) pra chamar quem ainda não bateu a meta de atividade do período.

Campos que podem ser usados no texto (preenchidos em atividade.py):
  {meta}        pontos que precisa passar pra ficar ativo
  {min_call}    minutos em call (desmutado) que valem 1 ponto
  {dias}        tempo que falta pro fim do período, já com a palavra ("5 dias", "1 dia")
  {inativos}    quantos ainda não bateram a meta, já com a palavra ("1 membro", "12 membros")
"""

MENSAGENS_INCENTIVO: list[str] = [
    "👋 Ei, sumido(a)! Ainda dá tempo de bater a meta do período: passe de **{meta} pontos** e entre pra lista de ativos. Bora trocar uma ideia aqui no chat!",
    "🚀 Bora acelerar! Cada mensagem no servidor vale **1 ponto** — é só conversar e a meta de **{meta}** vai chegando sem você nem perceber.",
    "🎙️ Sabia que **{min_call} minutos em call** valem 1 ponto? Entra numa call, fica desmutado e deixa o tempo trabalhar por você.",
    "⏳ Contagem regressiva: **{dias}** pro fim do período de atividade. Dá tempo de passar dos **{meta} pontos** — só não deixa pro último minuto!",
    "🔥 Tem **{inativos}** ainda na luta pra bater a meta. Entra nessa e mostra que o TryHarders RL também é a sua casa!",
    "💬 Manda um \"salve\" aí no chat! Conversar com a galera já conta ponto e ainda ajuda a gente a se conhecer melhor.",
    "🎮 Quer jogar mas não sabe com quem? Chama a galera na call! Além de jogo, você ainda soma pontos de atividade.",
    "🏆 Um time forte é feito de gente presente. Aparece mais por aqui — a meta são só **{meta} pontos** e você chega lá rapidinho.",
    "📈 Dica de ouro: um pouquinho por dia rende mais que tudo no último dia. Passa aqui, manda umas mensagens e fica de olho nos pontos!",
    "🤝 A gente sente sua falta! Volta pro chat, participa das conversas e ajuda a manter o servidor vivo.",
    "⚡ Meta do período: passar de **{meta} pontos**. Mensagens e tempo em call se somam — use os dois do jeito que preferir.",
    "🎧 Ficar em call ouvindo a galera jogar também conta! Só lembra de estar desmutado — a cada **{min_call} minutos** você ganha 1 ponto.",
    "🧠 Quer evoluir no Rocket League? Aqui é o lugar: trocar dica, marcar treino, chamar pra jogar. E de quebra você fica ativo(a)!",
    "📣 Aviso amigo: ainda tem gente abaixo da meta de atividade. Se for você, ainda dá tempo — ainda restam **{dias}** pra virar o jogo!",
    "😎 Ninguém quer ficar de fora da lista de ativos, né? Chega junto, conversa um pouco e garante seus pontos.",
    "🕹️ Tá com saudade de jogar em equipe? Chama alguém pra um 2v2 e entra na call — o clima é bom e os pontos vêm junto.",
    "🌟 Todo mundo começa do zero. Uma mensagem hoje, outra amanhã, e quando você ver já passou dos **{meta} pontos**.",
    "📅 Falta pouco pro período acabar (**{dias}**). Que tal aproveitar hoje pra participar mais do servidor?",
    "🗣️ Chat quieto fica sem graça! Solta uma opinião, um meme, uma jogada boa que você fez — vale ponto e vale a resenha.",
    "🎯 Missão do dia: mandar umas mensagens e passar um tempo em call. Simples assim — e você se aproxima dos **{meta} pontos**.",
    "💪 Nada de desanimar! Quem está abaixo da meta ainda tem tempo de correr atrás. A gente torce por você!",
    "🔊 As calls estão abertas! Entra, coloca o fone e vem jogar com a gente. A cada **{min_call} min** desmutado você marca 1 ponto.",
    "🎁 Ficar ativo(a) mostra que você faz parte do time de verdade. Entra na conversa e garante seu lugar na lista de ativos!",
    "🚗 Sem boost não dá pra ir longe! Aqui o boost é participação: mensagens e call te levam até a meta de **{meta} pontos**.",
    "🍿 Quem só observa também faz falta! Sai do modo espectador e participa das conversas, o pessoal vai gostar de te ver por aqui.",
    "🥇 Atividade é compromisso com o time. Falta pouco pra você provar que tá junto — passe de **{meta} pontos** e pronto!",
    "🌙 Sem tempo durante o dia? Aparece à noite na call que também conta ponto. O importante é aparecer!",
    "🧩 O servidor fica melhor com você presente. Volta, conversa, joga, e vamos juntos até o fim do período.",
    "📢 Atenção, inativos: ainda dá tempo! Mande mensagens no chat e entre em call — são duas formas fáceis de somar pontos.",
    "🎉 A galera ativa tá mandando bem, agora é a sua vez! Chega no chat e mostra que o TryHarders RL também é seu lugar.",
    "🔁 Não deixa a meta virar dor de cabeça: um pouquinho de participação todo dia resolve. Bora começar agora mesmo?",
    "🏁 Reta final chegando (**{dias}**)! Quem se mexer agora ainda passa dos **{meta} pontos** com folga. Vem com a gente!",
]

assert len(MENSAGENS_INCENTIVO) == 32, "precisa ter exatamente 32 mensagens"


# Mensagens que MARCAM um inativo específico (o bot sorteia um deles).
# Aqui {mencao} é obrigatório; {meta}, {min_call} e {dias} também funcionam.
MENSAGENS_MARCANDO: list[str] = [
    "Eai {mencao}, tudo certo? 👋 Bora conversar no chat?",
    "Fala {mencao}! Faz um tempinho que você não aparece por aqui. Bora trocar uma ideia no chat? 💬",
    "Opa {mencao}, sumiu hein! 😄 Chega aí no chat, a galera tá esperando você!",
    "{mencao}, e aí, bora jogar uma? 🎮 Entra numa call ou manda um salve no chat!",
    "Eai {mencao}! Sentimos sua falta por aqui 🚀 Passa no chat e conta como tá o Rocket League!",
    "Fala {mencao}, tudo bem? Bora bater um papo no chat e de quebra somar uns pontinhos de atividade? 😉",
    "{mencao}, dá uma passada no chat! Qualquer assunto vale: jogada boa, meme, dúvida de mecânica… 🧠",
    "Salve {mencao}! 🙌 Tá com tempo? Entra na call e joga com a gente!",
    "Eai {mencao}, como tá o rank? 📈 Vem contar no chat!",
    "Oi {mencao}! A meta de atividade são só **{meta} pontos**, dá tempo de sobra. Bora conversar no chat? 💪",
    "{mencao}, tá sumido(a)! 🔎 Aparece aí e manda um oi pra galera!",
    "Fala {mencao}! Que tal um 2v2 hoje? Chama alguém no chat e bora pra call 🎧",
    "Eai {mencao}, tudo tranquilo? Vem trocar uma ideia no chat, o servidor fica melhor com você por aqui! 🤝",
    "{mencao}, ainda dá tempo de ficar ativo(a) no período: faltam **{dias}**! Bora conversar? ⏳",
    "Opa {mencao}! 👀 Vi que você anda quieto(a). Solta um \"salve\" no chat e bora!",
    "{mencao}, bora sair do modo espectador? 🍿 Participa do chat que a gente quer te ouvir!",
    "Fala {mencao}! Qual foi sua melhor jogada recente? Conta pra gente no chat! 🏆",
    "Eai {mencao}! Entrar numa call desmutado por **{min_call} minutos** já vale 1 ponto. Bora? 🎙️",
    "{mencao}, saudade de você por aqui! 💙 Passa no chat e bora jogar junto!",
    "Salve {mencao}! Alguém precisa de dupla pra rankeada? Chega no chat e chama a galera! ⚽",
    "Eai {mencao}, bora movimentar esse chat? 🔥 Manda uma mensagem e começa a somar pontos!",
    "Fala {mencao}, tudo certo? Tá precisando de dica pro seu jogo? Pergunta no chat que a galera ajuda! 🧩",
    "{mencao}, dia bom pra jogar, né? ☀️ Bora aparecer no chat ou na call!",
    "Opa {mencao}! Chega mais, a conversa tá boa e falta você! 🗣️",
]

assert len(MENSAGENS_MARCANDO) >= 20 and all("{mencao}" in m for m in MENSAGENS_MARCANDO)


# Mensagens do CHAT PARADO: o bot manda uma delas no canal de incentivo quando
# ninguém fala há CHAT_PARADO_MINUTOS (ver atividade.py). São papo solto e
# aleatório pra puxar conversa (comida, bichos, perguntas bobas): não usam
# {campos} nem marcam ninguém. Pode editar/trocar à vontade, só manter 45.
MENSAGENS_CHAT_PARADO: list[str] = [
    "👋 Olá galera! Por que ninguém tá mandando mensagem? Tá todo mundo dormindo?",
    "🍇 Açaí com fruta ou açaí puro? Quero saber o lado de cada um!",
    "🤔 Se vocês pudessem comer só uma coisa pro resto da vida, o que seria?",
    "😴 Chat dormindo... alguém acorda aí e manda um oi!",
    "🍕 Pizza com ou sem borda recheada? Responde sem pensar!",
    "🦗 *grilos* ... ninguém? Sério? Alguém fala alguma coisa!",
    "🥤 Qual a bebida que vocês mais tomam? Guaraná, coca, suco, água?",
    "🐶 Cachorro ou gato? Defendam o seu time!",
    "🛌 Quem aqui já dormiu de tarde e acordou sem saber que dia era?",
    "🍫 Chocolate ao leite ou chocolate amargo? Tem que escolher um.",
    "📱 Qual foi a última coisa que vocês pesquisaram no Google? Sem mentir!",
    "🌧️ Como tá o tempo aí na cidade de vocês? Aqui no chat só tá chovendo silêncio.",
    "🍔 Qual o melhor lanche do mundo? Vou esperar a resposta de vocês.",
    "🎵 Qual música tá tocando no seu fone agora? Manda aí!",
    "😂 Qual foi a coisa mais aleatória que aconteceu com vocês essa semana?",
    "🧊 Gelo no refrigerante: sim ou não? Quero polêmica!",
    "🕐 Que horas vocês costumam dormir? Corujão ou acordando cedo?",
    "🥔 Batata frita ou batata doce? Escolhe um lado!",
    "🎬 Qual série ou filme vocês recomendam? Tô sem nada pra assistir.",
    "☕ Café ou chá? Ou nenhum dos dois e só energético?",
    "🍦 Qual o seu sabor de sorvete favorito? Se for coco, eu respeito.",
    "🤷 Sem assunto aqui... alguém sugere um tema pra gente conversar?",
    "🏖️ Praia ou campo? Pra onde vocês fugiriam hoje?",
    "🥚 O que veio primeiro, o ovo ou a galinha? Vocês têm 1 minuto pra resolver.",
    "🎂 Quando é o aniversário de vocês? Bora montar um calendário aqui!",
    "🧠 Pergunta que não faz sentido: se tomate é fruta, ketchup é geleia?",
    "🚿 Banho quente ou frio? Isso define o caráter de uma pessoa.",
    "🛒 O que vocês comprariam agora se ganhassem 100 reais?",
    "🗣️ Eita, que silêncio! Tô falando sozinho aqui, vem fazer companhia!",
    "🍉 Qual a melhor fruta? Vou contar os votos.",
    "📚 Qual a última coisa nova que vocês aprenderam? Pode ser besteira mesmo.",
    "✈️ Se tivessem que viajar agora pra qualquer lugar, pra onde iriam?",
    "🌮 Pastel, coxinha ou esfiha? Só um!",
    "🙃 Qual o apelido mais engraçado que vocês já tiveram?",
    "🥱 Alguém mais tá com preguiça hoje? Bora reclamar juntos no chat.",
    "🎲 Joguinho rápido: respondam com um emoji que descreve o seu dia!",
    "🍞 Pão com manteiga ou pão com queijo? Isso aqui é sério.",
    "🌙 Quem tá acordado a essa hora e por quê? Insônia, jogo ou fome?",
    "📺 Qual desenho ou programa de TV vocês assistiam quando eram crianças?",
    "🤝 Oi gente! Já que ninguém fala, eu pergunto: tá tudo bem com vocês?",
    "🍳 Ovo mexido, frito ou cozido? Qual o seu favorito?",
    "💤 Se o chat fosse uma pessoa, estaria dormindo agora. Alguém cutuca ele!",
    "🥭 Manga com sal, sim ou não? Tô esperando as brigas.",
    "🎤 Qual música vocês cantam no chuveiro? Sem vergonha, aqui é seguro!",
    "🍓 Morango com leite condensado ou com chantilly? Tô precisando de uma opinião!",
]

assert len(MENSAGENS_CHAT_PARADO) == 45, "precisa ter exatamente 45 mensagens"
