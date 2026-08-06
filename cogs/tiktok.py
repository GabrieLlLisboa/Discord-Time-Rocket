import discord
from discord.ext import commands, tasks
from discord import app_commands
import httpx
import json
import re
import os
import random


TIKTOK_CHANNEL_ID = 1515151647641178193
TIKTOK_USER          = "tryharders.rl"
VIDEO_NOVO_ROLE_ID   = 1515158913555894443
LAST_VIDEO_FILE   = "last_tiktok.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


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


def extrair_video_id(link: str) -> tuple[str, str] | None:
    """
    Tenta achar o ID numérico do post direto na URL — funciona pra links
    completos tanto de vídeo (tiktok.com/@user/video/123...) quanto de post
    em foto (tiktok.com/@user/photo/123...), que é outro formato que o
    TikTok usa desde que lançou o modo carrossel de fotos.
    Retorna (tipo, id) onde tipo é "video" ou "photo", ou None se não achar.
    """
    m = re.search(r'/(video|photo)/(\d+)', link)
    return (m.group(1), m.group(2)) if m else None


async def buscar_por_link(client: httpx.AsyncClient, link: str) -> dict | None:
    """
    Resolve um link de post do TikTok informado manualmente — vídeo ou foto
    —, inclusive links curtos (tipo vm.tiktok.com/xxxx ou vt.tiktok.com/xxxx,
    que redirecionam pro link completo), e busca o título via oEmbed.
    """
    url_final = link.strip()

    encontrado = extrair_video_id(url_final)
    if encontrado is None:


        try:
            resp = await client.get(url_final, headers=headers_aleatorios(), timeout=15, follow_redirects=True)
            url_final = str(resp.url)
            encontrado = extrair_video_id(url_final)
        except Exception as e:
            print(f"[TIKTOK] ⚠️  Falha ao resolver link curto '{link}': {e}")

    if encontrado is None:
        return None

    tipo, post_id = encontrado
    url_canonica = f"https://www.tiktok.com/@{TIKTOK_USER}/{tipo}/{post_id}"
    titulo = "Sem título"
    try:


        oembed_url = f"https://www.tiktok.com/oembed?url={url_final}"
        oe = await client.get(oembed_url, headers=headers_aleatorios(), timeout=10)
        if oe.status_code == 200:
            titulo = oe.json().get("title", "Sem título")
    except Exception as e:
        print(f"[TIKTOK] ⚠️  oEmbed falhou pro link manual: {e}")

    return {
        "id":     post_id,
        "titulo": titulo,
        "url":    url_final if f"/{tipo}/" in url_final else url_canonica,
        "via":    "link manual",
    }


async def via_oembed(client: httpx.AsyncClient) -> dict | None:
    """
    Usa a API oEmbed do TikTok para buscar o vídeo mais recente.
    Limitado — só valida se um ID conhecido ainda existe, mas útil
    para confirmar o título de um vídeo já detectado.
    Aqui usamos como pré-verificação de existência.
    """
    try:

        url  = f"https://www.tiktok.com/@{TIKTOK_USER}"
        resp = await client.get(url, headers=headers_aleatorios(), timeout=15)
        ids  = re.findall(r'/@' + re.escape(TIKTOK_USER) + r'/video/(\d+)', resp.text)
        if not ids:
            return None


        video_id = max(ids, key=int)

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


async def via_scraping_direto(client: httpx.AsyncClient) -> dict | None:
    try:
        url  = f"https://www.tiktok.com/@{TIKTOK_USER}"
        resp = await client.get(url, headers=headers_aleatorios(), timeout=20)
        html = resp.text


        match = re.search(
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if match:
            data     = json.loads(match.group(1))
            scope    = data.get("__DEFAULT_SCOPE__", {})

            for key in scope:
                if "user" in key.lower():
                    videos = scope[key].get("itemList", [])
                    if videos:


                        v = max(videos, key=lambda item: int(item.get("createTime", 0) or 0))
                        vid_id = v.get("id", "")
                        titulo = v.get("desc", "Sem título")
                        return {
                            "id":     vid_id,
                            "titulo": titulo,
                            "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
                            "via":    "scraping-json",
                        }


        ids = re.findall(r'/@' + re.escape(TIKTOK_USER) + r'/video/(\d+)', html)
        descs = re.findall(r'"desc"\s*:\s*"(.*?)"', html)
        if ids:
            video_id_mais_recente = max(ids, key=int)
            titulo = descs[0].encode().decode("unicode_escape") if descs and "\\u" in descs[0] else (descs[0] if descs else "Sem título")
            return {
                "id":     video_id_mais_recente,
                "titulo": titulo,
                "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{video_id_mais_recente}",
                "via":    "scraping-regex",
            }
    except Exception as e:
        print(f"[TIKTOK] ⚠️  Scraping direto falhou: {e}")
    return None


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


            itens_xml = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
            if not itens_xml:
                continue

            melhor = None
            for item_xml in itens_xml:
                id_match = re.search(r'/video/(\d+)', item_xml)
                if not id_match:
                    continue
                vid_id = id_match.group(1)
                if melhor is None or int(vid_id) > int(melhor["id"]):
                    titulo_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item_xml)
                    link_match   = re.search(r'<link>(https://www\.tiktok\.com/[^<]+)</link>', item_xml)
                    melhor = {
                        "id":     vid_id,
                        "titulo": titulo_match.group(1) if titulo_match else "Sem título",
                        "url":    link_match.group(1) if link_match else f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
                        "via":    f"proxitok ({instancia})",
                    }

            if melhor:
                return melhor
        except Exception as e:
            print(f"[TIKTOK] ⚠️  Proxitok {instancia} falhou: {e}")
            continue
    return None


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
            xml = resp.text


            entradas_xml = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
            candidatos = entradas_xml or [xml]

            melhor = None
            for entry_xml in candidatos:
                id_match = re.search(r'/video/(\d+)', entry_xml)
                if not id_match:
                    continue
                vid_id = id_match.group(1)
                if melhor is None or int(vid_id) > int(melhor["id"]):
                    t_match = re.search(r'<title[^>]*>(.*?)</title>', entry_xml, re.DOTALL)
                    melhor = {
                        "id":     vid_id,
                        "titulo": re.sub(r'<[^>]+>', '', t_match.group(1)).strip() if t_match else "Sem título",
                        "url":    f"https://www.tiktok.com/@{TIKTOK_USER}/video/{vid_id}",
                        "via":    "rssbridge",
                    }

            if melhor:
                return melhor
        except Exception as e:
            print(f"[TIKTOK] ⚠️  RSSBridge falhou: {e}")
            continue
    return None


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
        try:
            await self._checar_e_notificar()
        except Exception as e:


            print(f"[TIKTOK] ⚠️ Erro inesperado ao verificar novo vídeo: {e}")

    @verificar_tiktok.before_loop
    async def antes_do_loop(self):
        await self.bot.wait_until_ready()


    async def _checar_e_notificar(self, forcar: bool = False) -> str:
        """Retorna uma mensagem curta descrevendo o que aconteceu (pra usar na resposta do comando)."""
        canal = self.bot.get_channel(TIKTOK_CHANNEL_ID)
        if canal is None:
            print(f"[TIKTOK] ⚠️  Canal {TIKTOK_CHANNEL_ID} não encontrado.")
            return f"⚠️ Canal `{TIKTOK_CHANNEL_ID}` não encontrado."

        video = await buscar_ultimo_video()

        if video is None:
            self.falhas += 1
            print(f"[TIKTOK] ⚠️  Falha #{self.falhas} ao buscar vídeo.")
            return "⚠️ Não consegui buscar o vídeo mais recente agora (todas as estratégias falharam). Tenta de novo daqui a pouco."

        self.falhas = 0
        detalhe = f"(via {video['via']}, id `{video['id']}`)"


        if self.ultimo_video is None and not forcar:
            self.ultimo_video = video["id"]
            salvar_ultimo_video(video["id"])
            print(f"[TIKTOK] ✅ Primeiro vídeo registrado: {video['id']}")
            return f"✅ Primeiro vídeo registrado (não notificado, é o ponto de partida): **{video['titulo']}** {detalhe}"


        if video["id"] == self.ultimo_video and not forcar:
            print("[TIKTOK] 🔁 Nenhum vídeo novo.")
            return (
                f"🔁 Nenhum vídeo novo — o mais recente já foi postado antes: **{video['titulo']}** {detalhe}\n"
                f"-# Se você acha que tem vídeo novo mesmo assim (o site pode ter mudado ou bloqueado a "
                f"busca), usa `!atualizar-videos forcar` pra reenviar esse vídeo na marra."
            )


        self.ultimo_video = video["id"]
        salvar_ultimo_video(video["id"])

        cargo = canal.guild.get_role(VIDEO_NOVO_ROLE_ID)
        mencao = cargo.mention if cargo else ""

        embed = discord.Embed(
            title="🎵  A TryHarders RL postou um vídeo novo!",
            color=0xD4A843,
        )
        embed.add_field(name="📌  Título", value=video["titulo"], inline=False)
        embed.add_field(name="🔗  Link",   value=video["url"],    inline=False)
        embed.set_footer(text="TikTok • @tryharders.rl")
        embed.timestamp = discord.utils.utcnow()

        await canal.send(content=mencao if mencao else None, embed=embed)
        print(f"[TIKTOK] 🎉 Novo vídeo notificado: {video['titulo']}")
        return f"🎉 Vídeo notificado em {canal.mention}: **{video['titulo']}** {detalhe}"


    @commands.command(name="atualizar-videos")
    @commands.has_permissions(manage_guild=True)
    async def atualizar_videos(self, ctx: commands.Context, opcao: str = None):
        forcar = (opcao or "").lower() in ("forcar", "força", "forçar", "force")
        async with ctx.typing():
            try:
                resultado = await self._checar_e_notificar(forcar=forcar)
            except Exception as e:
                await ctx.send(f"❌ Erro ao checar vídeos: {e}")
                print(f"[TIKTOK] ⚠️ Erro no comando !atualizar-videos: {e}")
                return
        await ctx.send(resultado)

    @atualizar_videos.error
    async def atualizar_videos_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa de permissão de **Gerenciar Servidor** pra usar esse comando.")
        else:
            raise error


    @app_commands.command(name="video-novo", description="Anuncia manualmente um vídeo do TikTok a partir do link.")
    @app_commands.describe(link="Link do vídeo no TikTok (completo ou curto, tipo vm.tiktok.com/...)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def video_novo(self, interaction: discord.Interaction, link: str):
        await interaction.response.defer()

        canal = self.bot.get_channel(TIKTOK_CHANNEL_ID)
        if canal is None:
            await interaction.followup.send(f"⚠️ Canal `{TIKTOK_CHANNEL_ID}` não encontrado.")
            return

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                video = await buscar_por_link(client, link)
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao buscar esse link: {e}")
            print(f"[TIKTOK] ⚠️ Erro no /video-novo: {e}")
            return

        if video is None:
            await interaction.followup.send(
                "❌ Não consegui identificar o vídeo nesse link. Confere se é um link válido do TikTok "
                "(completo, tipo `tiktok.com/@usuario/video/123...`, ou curto, tipo `vm.tiktok.com/xxxx`)."
            )
            return


        if video["id"] == self.ultimo_video:
            await interaction.followup.send(
                f"🔁 Esse aí já foi anunciado antes: **{video['titulo']}** (id `{video['id']}`)."
            )
            return

        self.ultimo_video = video["id"]
        salvar_ultimo_video(video["id"])

        cargo = canal.guild.get_role(VIDEO_NOVO_ROLE_ID)
        mencao = cargo.mention if cargo else ""

        embed = discord.Embed(
            title="🎵  A TryHarders RL postou um vídeo novo!",
            color=0xD4A843,
        )
        embed.add_field(name="📌  Título", value=video["titulo"], inline=False)
        embed.add_field(name="🔗  Link",   value=video["url"],    inline=False)
        embed.set_footer(text="TikTok • @tryharders.rl")
        embed.timestamp = discord.utils.utcnow()

        await canal.send(content=mencao if mencao else None, embed=embed)
        print(f"[TIKTOK] 🎉 Vídeo anunciado manualmente via /video-novo: {video['titulo']}")
        await interaction.followup.send(f"✅ Anunciado em {canal.mention}: **{video['titulo']}**")

    @video_novo.error
    async def video_novo_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa de permissão de **Gerenciar Servidor** pra usar esse comando.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(TikTok(bot))
