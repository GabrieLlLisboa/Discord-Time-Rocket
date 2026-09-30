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
