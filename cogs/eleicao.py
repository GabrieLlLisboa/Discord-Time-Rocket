"""
Mensagens agendadas das eleições 2026 (1º turno: 04/10/2026).

- 03/10 (véspera): 2 mensagens, cada uma com uma proposta diferente do candidato Renan Santos (14).
  Propaganda é permitida até a véspera; NUNCA é enviada no dia 04/10.
- 04/10 (dia da votação): 3 mensagens neutras e informativas (sem pedir voto,
  sem citar candidato/número): documentos, roupa/celular e curiosidades.

Horários em UTC-3 (Brasília/Bahia; o Brasil não tem horário de verão).
O que já foi enviado fica em data/eleicao_enviadas.json, então reiniciar o
bot não reenvia nada. Se o bot ficar offline na hora, ele ainda envia até
2h depois do horário previsto; passou disso, a mensagem é descartada.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

CANAL_ID = 1511910275618443314
FUSO = timezone(timedelta(hours=-3))
TOLERANCIA = timedelta(hours=2)
ARQUIVO = os.path.join("data", "eleicao_enviadas.json")

DIA_VESPERA = (2026, 10, 3)
DIA_VOTACAO = (2026, 10, 4)

COR_VESPERA = 0x1E6FA8
COR_INFO = 0x2E7D32


def _dt(dia, hora, minuto=0):
    return datetime(*dia, hora, minuto, tzinfo=FUSO)


# id, horário, quando-é-permitido (dia), embed
MENSAGENS = [
    {
        "id": "vespera_proposta_saude",
        "quando": _dt(DIA_VESPERA, 18, 0),
        "dia_permitido": DIA_VESPERA,
        "titulo": "🗳️ Você conhece o Renan Santos (14)?",
        "texto": (
            "Candidato à Presidência pelo partido **Missão**, número **14**.\n\n"
            "🏥 **Proposta pra saúde:** digitalização completa do SUS, com "
            "**telemedicina**, **diagnóstico por inteligência artificial** e "
            "**prontuário eletrônico**, pra reduzir filas e levar atendimento "
            "a quem está longe dos grandes centros.\n\n"
            "🔎 Quer comparar? Veja o plano de governo de **todos** os candidatos "
            "no site do TSE e decida com calma. Amanhã é dia de votar!"
        ),
        "cor": COR_VESPERA,
    },
    {
        "id": "vespera_proposta_nordeste",
        "quando": _dt(DIA_VESPERA, 20, 30),
        "dia_permitido": DIA_VESPERA,
        "titulo": "🚀 Renan Santos (14): o plano pro Nordeste",
        "texto": (
            "Uma das apostas do plano de governo do candidato do **Missão** é criar "
            "**Zonas Econômicas Especiais no Nordeste**, para atrair indústria e "
            "gerar emprego:\n\n"
            "⚡ **Bahia:** mobilidade elétrica e semicondutores\n"
            "🌱 **Pernambuco:** hidrogênio verde e petroquímica\n"
            "🏗️ **Ceará e Pernambuco:** aço de baixo carbono, gesso e fertilizantes\n\n"
            "🔎 Compare as propostas de **todos** os candidatos no site do TSE. "
            "Amanhã é dia de votar!"
        ),
        "cor": COR_VESPERA,
    },
    {
        "id": "votacao_documentos",
        "quando": _dt(DIA_VOTACAO, 8, 30),
        "dia_permitido": DIA_VOTACAO,
        "titulo": "🪪 Hoje é dia de votar!",
        "texto": (
            "⏰ A votação vai das **8h às 17h** (horário de Brasília).\n\n"
            "📄 Leve um **documento oficial com foto**: RG/CIN, CNH, passaporte, "
            "carteira de trabalho física ou o **e-Título** com foto. "
            "O **título de eleitor em papel não é obrigatório**, e o documento "
            "pode estar vencido, desde que dê pra identificar você.\n\n"
            "🧾 Neste 1º turno são **6 votos**, nesta ordem: deputado federal, "
            "deputado estadual/distrital, senador (1ª vaga), senador (2ª vaga), "
            "governador e presidente."
        ),
        "cor": COR_INFO,
    },
    {
        "id": "votacao_candidatos",
        "quando": _dt(DIA_VOTACAO, 13, 35),
        "dia_permitido": DIA_VOTACAO,
        "titulo": "Já escolheu seu candidato à Presidência?",
        "texto": (
 "🇧🇷 **Candidatos à Presidência:**\n"
            "13 - Lula (PT)\n"
            "14 - Renan Santos (Missão)\n"
            "16 - Hertz Dias (PSTU)\n"
            "21 - Edmilson Costa (PCB)\n"
            "22 - Flávio Bolsonaro (PL)\n"
            "27 - Clariana Barão (DC)\n"
            "29 - Rui Costa Pimenta (PCO)\n"
            "30 - Romeu Zema (Novo)\n"
            "35 - Wilson Grassi (Democrata)\n"
            "55 - Ronaldo Caiado (PSD)\n"
            "70 - Augusto Cury (Avante)\n"
            "80 - Samara Martins (UP)"
        ),
        "cor": COR_INFO,
    },
    {
        "id": "votacao_roupa_celular",
        "quando": _dt(DIA_VOTACAO, 11, 30),
        "dia_permitido": DIA_VOTACAO,
        "titulo": "👕 Como ir vestido e o que levar",
        "texto": (
            "✅ **Pode:** ir com roupa confortável, usar camiseta, broche ou adesivo "
            "com a sua preferência política (manifestação individual e silenciosa) e "
            "levar uma **colinha** de papel com os números.\n\n"
            "🚫 **Não pode:** celular ou câmera dentro da cabine de votação, "
            "aglomeração de pessoas com roupas padronizadas, distribuir material de "
            "campanha ou abordar outros eleitores.\n\n"
            "💡 Dica: leve água, vá com tempo e, se puder, evite os horários de pico."
        ),
        "cor": COR_INFO,
    },
    {
        "id": "votacao_curiosidades",
        "quando": _dt(DIA_VOTACAO, 15, 0),
        "dia_permitido": DIA_VOTACAO,
        "titulo": "🧠 Curiosidades da eleição",
        "texto": (
            "🇧🇷 Mais de **158 milhões** de brasileiros estão aptos a votar neste "
            "1º turno.\n\n"
            "💼 Quem trabalha tem direito de se ausentar pelo tempo necessário para "
            "votar, **sem desconto no salário**.\n\n"
            "⏳ Ainda não votou? Corre! As urnas fecham às **17h**.\n\n"
            "📸 Votou? Compartilhe que cumpriu seu dever, mas sem divulgar o voto "
            "dos outros e sem celular na cabine!"
        ),
        "cor": COR_INFO,
    },
]


def _carregar() -> set:
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError):
        return set()


def _salvar(enviadas: set):
    os.makedirs(os.path.dirname(ARQUIVO), exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(sorted(enviadas), f)


class Eleicao(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enviadas = _carregar()
        self.verificar.start()

    def cog_unload(self):
        self.verificar.cancel()

    @tasks.loop(seconds=30)
    async def verificar(self):
        agora = datetime.now(FUSO)
        for msg in MENSAGENS:
            if msg["id"] in self.enviadas:
                continue
            if agora < msg["quando"]:
                continue
            # Passou da tolerância: descarta pra nunca mandar fora de hora.
            if agora > msg["quando"] + TOLERANCIA:
                self.enviadas.add(msg["id"])
                _salvar(self.enviadas)
                print(f"[ELEICAO] ⏭️ {msg['id']} descartada (fora da janela).")
                continue
            # Trava de segurança: só envia no dia permitido.
            if (agora.year, agora.month, agora.day) != msg["dia_permitido"]:
                continue

            canal = self.bot.get_channel(CANAL_ID)
            if canal is None:
                try:
                    canal = await self.bot.fetch_channel(CANAL_ID)
                except discord.HTTPException as e:
                    print(f"[ELEICAO] ❌ Canal {CANAL_ID} inacessível: {e}")
                    return
            embed = discord.Embed(
                title=msg["titulo"], description=msg["texto"], colour=msg["cor"]
            )
            try:
                await canal.send(embed=embed)
            except discord.HTTPException as e:
                print(f"[ELEICAO] ❌ Falha ao enviar {msg['id']}: {e}")
                continue
            self.enviadas.add(msg["id"])
            _salvar(self.enviadas)
            print(f"[ELEICAO] ✅ {msg['id']} enviada.")

    @verificar.before_loop
    async def _esperar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Eleicao(bot))
