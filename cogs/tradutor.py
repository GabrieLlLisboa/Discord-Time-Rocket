"""
Módulo: Ponte de tradução PT <-> EN entre dois canais
Arquivo: cogs/tradutor.py

Regra:
  • Canal PT (CANAL_PT_ID): toda mensagem de texto mandada aqui, por
    QUALQUER pessoa, é traduzida pro inglês e republicada no canal EN.
  • Canal EN (CANAL_EN_ID): só é traduzida de volta pro português (e
    republicada no canal PT) se quem mandou tiver o cargo CARGO_INGLES_ID
    — assim uma pessoa qualquer não dispara tradução reversa sem querer.

Usa o endpoint não-oficial do Google Tradutor (o mesmo que bibliotecas
como googletrans usam por baixo dos panos) — não precisa de chave de API.
Se a tradução falhar por qualquer motivo, a mensagem simplesmente não é
replicada; não trava o bot nem avisa erro pro usuário no canal.

Antes de mandar pro tradutor, o texto passa por um pré-processamento:
  1. Protege menções (@fulano), emojis customizados, canais e links —
     eles saem intactos, sem o tradutor tentar "traduzir" um ID ou quebrar
     um link.
  2. Normaliza risada (kkkkk, rsrsrs) e letras esticadas (muuuuito) pra não
     confundir o tradutor.
  3. Expande gírias/abreviações comuns de chat em português (dps, blz,
     vlw, etc.) pela forma completa.
Depois de traduzido, os tokens protegidos (menções/emojis/links) voltam
pro lugar original.
"""

from __future__ import annotations

import re
import time

import discord
from discord.ext import commands
import httpx

# Canal onde a galera fala português
CANAL_PT_ID = 1511910275618443314

# Canal "pra ingleses" — só quem tem o cargo de idioma Inglês dispara a
# tradução reversa (EN -> PT) a partir daqui
CANAL_EN_ID = 1525864485884137503
CARGO_INGLES_ID = 1525312330831892481


# ═══════════════════════════════════════════════════════════════════════
#  1. GÍRIAS / ABREVIAÇÕES — expandidas ANTES de traduzir PT -> EN
# ═══════════════════════════════════════════════════════════════════════
GIRIAS = {
    "dps": "depois",
    "blz": "beleza",
    "blza": "beleza",
    "vlw": "valeu",
    "vlws": "valeu",
    "flw": "falou",
    "flws": "falou",
    "vc": "você",
    "vcs": "vocês",
    "tb": "também",
    "tbm": "também",
    "tmb": "também",
    "pq": "porque",
    "pqp": "puta que pariu",
    "mt": "muito",
    "mto": "muito",
    "mta": "muita",
    "mts": "muitos",
    "td": "tudo",
    "tds": "todos",
    "to": "estou",
    "tô": "estou",
    "ta": "está",
    "tá": "está",
    "tava": "estava",
    "tamo": "estamos",
    "bora": "vamos",
    "sla": "sei lá",
    "slc": "sei lá cara",
    "msg": "mensagem",
    "pfv": "por favor",
    "pf": "por favor",
    "pfvr": "por favor",
    "obg": "obrigado",
    "obgd": "obrigado",
    "obgda": "obrigada",
    "vdd": "verdade",
    "glr": "galera",
    "gnt": "gente",
    "hj": "hoje",
    "agr": "agora",
    "qq": "qualquer",
    "qnd": "quando",
    "qm": "quem",
    "cmo": "como",
    "cmg": "comigo",
    "ctg": "contigo",
    "sdd": "saudade",
    "sdds": "saudades",
    "bj": "beijo",
    "bjo": "beijo",
    "bjs": "beijos",
    "abs": "abraço",
    "fds": "final de semana",
    "dnv": "de novo",
    "oq": "o que",
    "neh": "né",
    "add": "adicionar",
    "tmj": "tamo junto",
    "fmz": "de boa",
    "susp": "suspeito",
    "n": "não",
    "naum": "não",
    "eh": "é",
    "aki": "aqui",
    "aew": "aí",
    "ae": "aí",
    "rlx": "relaxa",
    "mlk": "moleque",
    "mds": "meu deus",
    "sqn": "só que não",
    "kd": "cadê",
    "cad": "cadê",
    "cê": "você",
    "ce": "você",
    "pk": "porque",
    "pls": "por favor",
    "obgg": "obrigado",
    "q": "que",
    "qlq": "qualquer",
    "aq": "aqui",
    "agnt": "a gente",
    "cntg": "contigo",
    "img": "imagem",
    "ft": "foto",
    "fts": "fotos",
    "adm": "administrador",
    "mod": "moderador",
    "sv": "servidor",
    "srv": "servidor",
    "dc": "Discord",
    "yt": "YouTube",
    "insta": "Instagram",
    "wpp": "WhatsApp",
    "zap": "WhatsApp",
    "zapzap": "WhatsApp",
    "agente": "a gente",
    "derrepente": "de repente",
    "comcerteza": "com certeza",
    "concerteza": "com certeza",
    "enves": "em vez",
    "inves": "em vez",
    "atravez": "através",
    "muinto": "muito",
    "muinta": "muita",
    "menas": "menos",
    "poblema": "problema",
    "probrema": "problema",
    "escessão": "exceção",
    "excessão": "exceção",
    "conheser": "conhecer",
    "conheçer": "conhecer",
    "fasso": "faço",
    "faso": "faço",
    "faser": "fazer",
    "quizer": "quiser",
    "quisse": "quisesse",
    "quiz": "quis",
    "trousse": "trouxe",
    "trouce": "trouxe",
    "trouse": "trouxe",
    "truxe": "trouxe",
    "seje": "seja",
    "esteje": "esteja",
    "estejem": "estejam",
    "teveu": "teve",
    "houveram": "houve",
    "nao": "não",
    "naun": "não",
    "num": "não",
    "nn": "não",
    "ñ": "não",
    "simm": "sim",
    "simmm": "sim",
    "ss": "sim",
    "belezaa": "beleza",
    "bleza": "beleza",
    "belza": "beleza",
    "valeuuu": "valeu",
    "vlww": "valeu",
    "manoo": "mano",
    "mno": "mano",
    "kra": "cara",
    "kara": "cara",
    "tp": "tipo",
    "tipu": "tipo",
    "onti": "ontem",
    "amanha": "amanhã",
    "agrr": "agora",
    "aqi": "aqui",
    "akii": "aqui",
    "alii": "ali",
    "issu": "isso",
    "iso": "isso",
    "esa": "essa",
    "ese": "esse",
    "msm": "mesmo",
    "msmo": "mesmo",
    "memo": "mesmo",
    "mermo": "mesmo",
    "parabens": "parabéns",
    "niver": "aniversário",
    "aniver": "aniversário",
    "iskola": "escola",
    "prof": "professor",
    "profe": "professora",
    "atv": "atividade",
    "trab": "trabalho",
    "facul": "faculdade",
    "uni": "universidade",
    "pc": "computador",
    "cel": "celular",
    "fone": "telefone",
    "net": "internet",
    "vd": "vídeo",
    "vds": "vídeos",
    "lnk": "link",
    "dl": "download",
    "up": "upload",
    "cfg": "configuração",
    "configs": "configurações",
    "mc": "Minecraft",
    "rbx": "Roblox",
    "tt": "TikTok",
    "xau": "tchau",
    "amr": "amor",
    "miga": "amiga",
    "mig": "amigo",
    "dms": "demais",
    "flz": "feliz",
    "algm": "alguém",
    "algma": "alguma",
    "ngm": "ninguém",
    "qnt": "quanto",
    "cm": "como",
    "ond": "onde",
    "vm": "vem",
    "vms": "vamos",
}

# Ordena por tamanho decrescente pra evitar que uma gíria menor "coma"
# parte de uma maior no regex (ex: "vc" dentro de "vcs")
_PADRAO_GIRIAS = re.compile(
    r"\b(" + "|".join(re.escape(g) for g in sorted(GIRIAS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _expandir_girias(texto: str) -> str:
    """Troca gírias/abreviações conhecidas pela forma completa,
    preservando a capitalização original (maiúscula/minúscula)."""

    def _sub(match: re.Match) -> str:
        original = match.group(0)
        expandido = GIRIAS.get(original.lower())
        if expandido is None:
            return original
        # Só considera "GRITANDO" (tudo maiúsculo) se tiver mais de uma
        # letra — uma letra maiúscula sozinha (ex: "Q" no início de frase)
        # é só a primeira maiúscula normal, não CAPS LOCK
        if len(original) > 1 and original.isupper():
            return expandido.upper()
        if original[0].isupper():
            return expandido[0].upper() + expandido[1:]
        return expandido

    return _PADRAO_GIRIAS.sub(_sub, texto)


# ═══════════════════════════════════════════════════════════════════════
#  2. NORMALIZAÇÃO — risada e letras esticadas
# ═══════════════════════════════════════════════════════════════════════
_PADRAO_RISADA = re.compile(
    r"\b(?:[kK]{3,}|[hH](?:[aA][hH]?)+|(?:[rR][sS]){2,}|[rR][sS]{2,})\b"
)
_PADRAO_LETRA_ESTICADA = re.compile(r"(.)\1{3,}")  # ex: "muuuuuito" (4+ repetições seguidas)


def _normalizar_texto(texto: str) -> str:
    # "kkkkkk", "hahaha", "rsrsrs" -> "haha" (o tradutor entende melhor
    # e não gera um resultado aleatório tentando traduzir "kkkkkk")
    texto = _PADRAO_RISADA.sub("haha", texto)
    # "muuuuuito" -> "muiito" (encolhe repetição de 4+ letras pra 2,
    # mantém um pouco da ênfase sem confundir o tradutor)
    texto = _PADRAO_LETRA_ESTICADA.sub(r"\1\1", texto)
    return texto


# ═══════════════════════════════════════════════════════════════════════
#  3. PROTEÇÃO DE TOKENS — menções, emojis, canais e links não podem
#     passar pelo tradutor (ele quebra/mistura os IDs e URLs)
# ═══════════════════════════════════════════════════════════════════════
_PADRAO_PROTEGER = re.compile(
    r"(https?://\S+|<a?:\w+:\d+>|<@!?\d+>|<#\d+>|<@&\d+>)"
)
_PADRAO_TOKEN = re.compile(r"Z0X(\d+)X0Z")


def _proteger_tokens(texto: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def _sub(match: re.Match) -> str:
        tokens.append(match.group(0))
        return f"Z0X{len(tokens) - 1}X0Z"

    return _PADRAO_PROTEGER.sub(_sub, texto), tokens


def _restaurar_tokens(texto: str, tokens: list[str]) -> str:
    def _sub(match: re.Match) -> str:
        idx = int(match.group(1))
        return tokens[idx] if idx < len(tokens) else match.group(0)

    return _PADRAO_TOKEN.sub(_sub, texto)


# ═══════════════════════════════════════════════════════════════════════
#  4. TRADUÇÃO — cliente HTTP persistente (bem mais rápido que abrir uma
#     conexão nova a cada mensagem), com 1 retry rápido, e um cache
#     simples em memória pra frases repetidas ("gg", "bom jogo" etc.)
# ═══════════════════════════════════════════════════════════════════════
_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_CACHE_TTL = 60 * 30  # meia hora
_CACHE_MAX = 500

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def _cache_get(texto: str, destino: str) -> str | None:
    chave = (texto, destino)
    item = _CACHE.get(chave)
    if item is None:
        return None
    valor, expira_em = item
    if time.monotonic() > expira_em:
        _CACHE.pop(chave, None)
        return None
    return valor


def _cache_set(texto: str, destino: str, valor: str) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)  # remove o mais antigo
    _CACHE[(texto, destino)] = (valor, time.monotonic() + _CACHE_TTL)


async def _traduzir(client: httpx.AsyncClient, texto: str, idioma_origem: str, idioma_destino: str) -> str | None:
    """Traduz `texto` do idioma `idioma_origem` pro `idioma_destino` ('en' ou 'pt').
    Retorna None se der qualquer erro (rede fora do ar, resposta
    inesperada, etc.) — quem chama trata isso simplesmente não
    republicando a mensagem.

    IMPORTANTE: `idioma_origem` é sempre explícito (nunca 'auto'). Frases
    curtas e ambíguas como 'bom dia' às vezes são detectadas erroneamente
    como outro idioma pelo Google (ex: 'bom' e 'dia' também existem em
    indonésio/malaio, com significados bem diferentes — foi assim que
    'bom dia' virou 'Bomb him' antes dessa correção). Como já sabemos de
    qual canal a mensagem veio, não faz sentido deixar o Google adivinhar.
    """
    if not texto or not texto.strip():
        return None

    chave_cache = f"{idioma_origem}->{idioma_destino}"
    em_cache = _cache_get(texto, chave_cache)
    if em_cache is not None:
        return em_cache

    for tentativa in range(2):  # 1 tentativa + 1 retry rápido
        try:
            resp = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": idioma_origem,
                    "tl": idioma_destino,
                    "dt": "t",
                    "q": texto,
                },
                headers=_HEADERS,
            )
            resp.raise_for_status()
            dados = resp.json()
            # dados[0] é uma lista de segmentos [texto_traduzido, texto_original, ...]
            traduzido = "".join(segmento[0] for segmento in dados[0] if segmento[0])
            _cache_set(texto, chave_cache, traduzido)
            return traduzido
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
            if tentativa == 0:
                continue  # tenta mais uma vez rapidinho antes de desistir
            print(f"[TRADUTOR] ⚠️ Erro ao traduzir: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════
#  Cog
# ═══════════════════════════════════════════════════════════════════════
class Tradutor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cliente HTTP único e reutilizado (bem mais rápido do que abrir
        # uma conexão TLS nova a cada mensagem mandada no canal)
        self.client = httpx.AsyncClient(timeout=8)

    async def cog_unload(self):
        await self.client.aclose()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora o próprio bot (evita loop com as mensagens que ele mesmo
        # manda como tradução) e mensagens de webhook
        if message.author.bot or message.webhook_id is not None:
            return

        # Ignora comandos (!algumacoisa) — não faz sentido "traduzir" isso
        prefixo = self.bot.command_prefix
        if isinstance(prefixo, str) and message.content.startswith(prefixo):
            return

        if message.channel.id == CANAL_PT_ID:
            await self._retransmitir(message, destino_id=CANAL_EN_ID, idioma_origem="pt", idioma_destino="en", bandeira="🇬🇧")

        elif message.channel.id == CANAL_EN_ID:
            cargos_do_autor = {r.id for r in getattr(message.author, "roles", [])}
            if CARGO_INGLES_ID not in cargos_do_autor:
                return  # só quem tem o cargo de Inglês dispara a tradução reversa
            await self._retransmitir(message, destino_id=CANAL_PT_ID, idioma_origem="en", idioma_destino="pt", bandeira="🇧🇷")

    async def _retransmitir(self, message: discord.Message, destino_id: int, idioma_origem: str, idioma_destino: str, bandeira: str):
        texto_original = message.content
        if not texto_original or not texto_original.strip():
            return  # mensagem só com imagem/anexo/embed — nada de texto pra traduzir

        # 1. Protege menções, emojis, canais e links antes de mexer no texto
        texto, tokens = _proteger_tokens(texto_original)

        # 2. Normaliza risada e letras esticadas
        texto = _normalizar_texto(texto)

        # 3. Só faz sentido expandir gírias em português quando a origem é
        #    o texto em português (ou seja, traduzindo PT -> EN)
        if idioma_destino == "en":
            texto = _expandir_girias(texto)

        # Se depois de tirar os tokens protegidos não sobrou texto de
        # verdade (ex: mensagem que era só um link ou só uma menção),
        # não há nada útil pra traduzir
        if not _PADRAO_TOKEN.sub("", texto).strip():
            return

        traduzido = await _traduzir(self.client, texto, idioma_origem, idioma_destino)
        if not traduzido:
            return

        # 4. Devolve menções/emojis/links pro lugar
        traduzido = _restaurar_tokens(traduzido, tokens)

        canal_destino = self.bot.get_channel(destino_id)
        if canal_destino is None:
            try:
                canal_destino = await self.bot.fetch_channel(destino_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        embed = discord.Embed(description=traduzido, color=0x5865F2)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"{bandeira} Traduzido automaticamente")

        try:
            await canal_destino.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[TRADUTOR] ⚠️ Erro ao enviar tradução em #{canal_destino}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tradutor(bot))
