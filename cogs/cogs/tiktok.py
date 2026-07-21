import discord
from discord.ext import commands, tasks
import httpx
import json
import re
import os
import random

# ─────────────────────────────────────────────
#  Cog: TikTok Notifier — Multi-layer fallback
#  Arquivo: cogs/tiktok.py
#  Estratégias em ordem de prioridade:
#    1. TikTok oEmbed API (oficial, sem auth)
#    2. Scraping direto com rotate de User-Agents
#    3. Scraping via proxy público
#    4. RSS via Proxitok (instância alternativa)
#    5. RSS via TikTok RSS Bridge
# ─────────────────────────────────────────────

TIKTOK_CHANNEL_ID = 1515151647641178193
TIKTOK_USER          = "ignition.rl"
VIDEO_NOVO_ROLE_ID   = 1515158913555894443
LAST_VIDEO_FILE   = "last_tiktok.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# Instâncias públicas do Proxitok (alternativa ao TikTok)
PROXITOK_INSTANCES = [
    "https://proxitok.pussthecat.org",
    "https://proxitok.privacy.com.de",
    "https://proxitok.esmailelbob.xyz",
    "https://tok.whatever.social",
]


def carregar_ultimo_video() -> str | None:
    if os.path.exists(LAST_VIDEO_FILE):
        with open(LAST_VIDEO_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def salvar_ultimo_video(video_id: str):
    with open(LAST_VIDEO_FILE, "w", encoding="utf-8") as f:
        f.write(video_id)


def headers_aleatorios() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Referer": "https://www.tiktok.com/",
        "sec-fetch-site": "none",
        "sec-fetch-mode": "navigate",
    }


# ── Estratégia 1: oEmbed API oficial ──────────────────────────────────────────
async def via_oembed(client: httpx.AsyncClient) -> dict | None:
    """
    Usa a API oEmbed do TikTok para buscar o vídeo mais recente.
    Limitado — só valida se um ID conhecido ainda existe, mas útil
    para confirmar o título de um vídeo já detectado.
    Aqui usamos como pré-verificação de existência.
    """
    try:
        # Busca o HTML do perfil primeiro para pegar o ID
        url  = f"https://www.tiktok.com/@{TIKTOK_USER}"
        resp = await client.get(url, headers=headers_aleatorios(), timeout=15)
        ids  = re.findall(r'/@' + re.escape(TIKTOK_USER) + r'/video/(\d+)', resp.text)
        if not ids:
            return None

        video_id = ids[0]
        # Valida com oEmbed
        oembed_url = f"https://www.tiktok.com/oembed?url=https://www.tiktok.com/@{TIKTOK_USER}/video/{video_id}"
        oe = await client.get(oembed_url, headers=headers_aleatorios(), timeout=10)
        if oe.status_code == 200:
            data = oe.json()
            return {
                "id":     video_id,
                "titulo": data.get("title", "Sem título"),
                "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{video_id}",
                "via":    "oEmbed",
            }
    except Exception as e:
        print(f"[TIKTOK] ⚠️  oEmbed falhou: {e}")
    return None


# ── Estratégia 2: Scraping direto com JSON embutido ───────────────────────────
async def via_scraping_direto(client: httpx.AsyncClient) -> dict | None:
    try:
        url  = f"https://www.tiktok.com/@{TIKTOK_USER}"
        resp = await client.get(url, headers=headers_aleatorios(), timeout=20)
        html = resp.text

        # Tenta extrair do JSON universal injetado pelo TikTok
        match = re.search(
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if match:
            data     = json.loads(match.group(1))
            scope    = data.get("__DEFAULT_SCOPE__", {})
            # Navega pela estrutura de dados do perfil
            for key in scope:
                if "user" in key.lower():
                    videos = scope[key].get("itemList", [])
                    if videos:
                        v = videos[0]
                        vid_id = v.get("id", "")
                        titulo = v.get("desc", "Sem título")
                        return {
                            "id":     vid_id,
                            "titulo": titulo,
                            "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
                            "via":    "scraping-json",
                        }

        # Fallback: regex direta no HTML
        ids = re.findall(r'/@' + re.escape(TIKTOK_USER) + r'/video/(\d+)', html)
        descs = re.findall(r'"desc"\s*:\s*"(.*?)"', html)
        if ids:
            titulo = descs[0].encode().decode("unicode_escape") if descs and "\\u" in descs[0] else (descs[0] if descs else "Sem título")
            return {
                "id":     ids[0],
                "titulo": titulo,
                "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{ids[0]}",
                "via":    "scraping-regex",
            }
    except Exception as e:
        print(f"[TIKTOK] ⚠️  Scraping direto falhou: {e}")
    return None


# ── Estratégia 3: Proxitok RSS ────────────────────────────────────────────────
async def via_proxitok(client: httpx.AsyncClient) -> dict | None:
    instancias = PROXITOK_INSTANCES.copy()
    random.shuffle(instancias)
    for instancia in instancias:
        try:
            url  = f"{instancia}/@{TIKTOK_USER}/rss"
            resp = await client.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=15)
            if resp.status_code != 200:
                continue
            xml = resp.text

            # Extrai o primeiro item do RSS
            titulo_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', xml)
            link_match   = re.search(r'<link>(https://www\.tiktok\.com/[^<]+)</link>', xml)
            id_match     = re.search(r'/video/(\d+)', xml)

            if id_match:
                video_id = id_match.group(1)
                titulo   = titulo_match.group(1) if titulo_match else "Sem título"
                link     = link_match.group(1)   if link_match   else f"https://www.tiktok.com/@{TIKTOK_USER}/video/{video_id}"
                return {
                    "id":     video_id,
                    "titulo": titulo,
                    "url":    link,
                    "via":    f"proxitok ({instancia})",
                }
        except Exception as e:
            print(f"[TIKTOK] ⚠️  Proxitok {instancia} falhou: {e}")
            continue
    return None


# ── Estratégia 4: RSSBridge ───────────────────────────────────────────────────
async def via_rssbridge(client: httpx.AsyncClient) -> dict | None:
    bridges = [
        f"https://rssbridge.org/?action=display&bridge=TikTok&username={TIKTOK_USER}&format=Atom",
        f"https://rss-bridge.org/bridge01/?action=display&bridge=TikTok&username={TIKTOK_USER}&format=Atom",
    ]
    for url in bridges:
        try:
            resp = await client.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=15)
            if resp.status_code != 200:
                continue
            xml      = resp.text
            id_match = re.search(r'/video/(\d+)', xml)
            t_match  = re.search(r'<title[^>]*>(.*?)</title>', xml, re.DOTALL)
            if id_match:
                video_id = id_match.group(1)
                titulo   = re.sub(r'<[^>]+>', '', t_match.group(1)).strip() if t_match else "Sem título"
                return {
                    "id":     video_id,
                    "titulo": titulo,
                    "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{video_id}",
                    "via":    "rssbridge",
                }
        except Exception as e:
            print(f"[TIKTOK] ⚠️  RSSBridge falhou: {e}")
            continue
    return None


# ── Orquestrador: tenta todas as estratégias em sequência ─────────────────────
async def buscar_ultimo_video() -> dict | None:
    estrategias = [via_oembed, via_scraping_direto, via_proxitok, via_rssbridge]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for estrategia in estrategias:
            resultado = await estrategia(client)
            if resultado:
                print(f"[TIKTOK] ✅ Vídeo obtido via {resultado['via']}")
                return resultado
    print("[TIKTOK] ❌ Todas as estratégias falharam.")
    return None


# ── Cog ───────────────────────────────────────────────────────────────────────
class TikTok(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot          = bot
        self.ultimo_video = carregar_ultimo_video()
        self.falhas       = 0
        self.verificar_tiktok.start()

    def cog_unload(self):
        self.verificar_tiktok.cancel()

    @tasks.loop(minutes=30)
    async def verificar_tiktok(self):
        await self.bot.wait_until_ready()

        canal = self.bot.get_channel(TIKTOK_CHANNEL_ID)
        if canal is None:
            print(f"[TIKTOK] ⚠️  Canal {TIKTOK_CHANNEL_ID} não encontrado.")
            return

        video = await buscar_ultimo_video()

        if video is None:
            self.falhas += 1
            print(f"[TIKTOK] ⚠️  Falha #{self.falhas} ao buscar vídeo.")
            return

        self.falhas = 0  # reset contador de falhas

        # Primeira execução — só salva
        if self.ultimo_video is None:
            self.ultimo_video = video["id"]
            salvar_ultimo_video(video["id"])
            print(f"[TIKTOK] ✅ Primeiro vídeo registrado: {video['id']}")
            return

        # Vídeo novo!
        if video["id"] != self.ultimo_video:
            self.ultimo_video = video["id"]
            salvar_ultimo_video(video["id"])

            cargo = canal.guild.get_role(VIDEO_NOVO_ROLE_ID)
            mencao = cargo.mention if cargo else ""

            embed = discord.Embed(
                title="🎵  A Ignition RL postou um vídeo novo!",
                color=0xD4A843,
            )
            embed.add_field(name="📌  Título", value=video["titulo"], inline=False)
            embed.add_field(name="🔗  Link",   value=video["url"],    inline=False)
            embed.set_footer(text="TikTok • @ignition.rl")
            embed.timestamp = discord.utils.utcnow()

            await canal.send(content=mencao if mencao else None, embed=embed)
            print(f"[TIKTOK] 🎉 Novo vídeo notificado: {video['titulo']}")
        else:
            print(f"[TIKTOK] 🔁 Nenhum vídeo novo.")

    @verificar_tiktok.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TikTok(bot))
