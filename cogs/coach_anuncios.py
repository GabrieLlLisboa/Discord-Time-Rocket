"""
Módulo: Anúncios de divulgação dos coaches
Arquivo: cogs/coach_anuncios.py

Texto de divulgação de cada coach (chave do coach -> mensagem). Quando o bot
inicia, coach_commands.py envia a mensagem UMA vez no canal do coach (o ID
fica salvo em data/coaches.json) e depois recoloca "📊 Estatísticas" e
"🛒 Comprar Atendimento" como as duas últimas mensagens do canal.

Pra reenviar um anúncio (ex.: mudou o preço), apague a mensagem antiga no
canal e o campo "anuncio_message_id" do coach em data/coaches.json.
"""

ANUNCIOS: dict[str, str] = {
    "lonely": (
        "🚀 COACHING DE ROCKET LEAGUE | PROMOÇÃO DE LANÇAMENTO\n"
        "\n"
        "Fala! Eu sou o Lonely.\n"
        "\n"
        "🎮 Tenho cerca de 1.400 horas de Rocket League e atualmente sou GC2 no 2v2.\n"
        "\n"
        "🧠 Meu objetivo como coach é analisar seu gameplay e identificar os erros que estão "
        "impedindo sua evolução, mostrando de forma prática e personalizada como corrigi-los.\n"
        "\n"
        "Durante o coaching, podemos trabalhar:\n"
        "\n"
        "⚡ Tomada de decisão\n"
        "🛡️ Posicionamento\n"
        "🎯 Finalizações e passes\n"
        "🚗 Mecânicas\n"
        "🧠 Leitura de jogo\n"
        "⏱️ Controle de ritmo\n"
        "📈 Adaptação ao adversário\n"
        "\n"
        "💥 PROMOÇÃO DE LANÇAMENTO\n"
        "\n"
        "🔥 Apenas para os 7 primeiros clientes!\n"
        "\n"
        "💰 TABELA DE PREÇOS\n"
        "\n"
        "🔥 PREÇOS DE LANÇAMENTO\n"
        "\n"
        "🎮 1v1 com dicas — 1 hora\n"
        "R$12\n"
        "\n"
        "📼 Análise de replay — 1 hora\n"
        "R$12\n"
        "\n"
        "⚔️ 1v1 + análise de replay — 30 min cada\n"
        "R$15\n"
        "\n"
        "\n"
        "---\n"
        "\n"
        "💵 PREÇOS APÓS A PROMOÇÃO\n"
        "\n"
        "🎮 1v1 com dicas — 1 hora\n"
        "R$25\n"
        "\n"
        "📼 Análise de replay — 1 hora\n"
        "R$25\n"
        "\n"
        "⚔️ 1v1 + análise de replay — 30 min cada\n"
        "R$27\n"
        "\n"
        "Se você está preso no seu rank e quer entender o que realmente está impedindo sua "
        "evolução, me chama no privado.\n"
        "\n"
        "📩 7 vagas disponíveis."
    ),
}
