"""
Módulo: Canal de notícias
Arquivo: cogs/noticias.py

Busca notícias de Rocket League / RLCS em feeds RSS (Google Notícias) a cada
30 minutos e posta no canal de notícias só o que ainda NÃO foi postado.

Como escolher o canal:
  • /noticias_canal  — slash command (só administradores), salva em
                       data/noticias.json; ou
  • NOTICIAS_CHANNEL_ID no .env; ou
  • preencher CANAL_NOTICIAS_ID abaixo.

Sem repetição: cada notícia é identificada pelo título (normalizado), então a
mesma matéria publicada por vários sites sai uma vez só. O histórico
(até MAX_VISTAS) fica em data/noticias.json e sobrevive a reinícios.

Na PRIMEIRA rodada o bot posta só as PRIMEIRA_RODADA_QTD notícias mais
recentes e marca o resto como vistas, pra não inundar o canal de uma vez.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.json_store import ler_json, salvar_json

CONFIG_PATH = "data/noticias.json"

# Canal das notícias (0 = usa o que foi definido por /noticias_canal)
CANAL_NOTICIAS_ID = int(os.getenv("NOTICIAS_CHANNEL_ID", 0))

INTERVALO_MINUTOS = 30       # de quanto em quanto tempo o bot procura notícia nova
MAX_POR_RODADA = 2           # máximo de notícias postadas por rodada
PRIMEIRA_RODADA_QTD = 3      # quantas postar na primeiríssima rodada
MAX_IDADE_DIAS = 7           # ignora notícia mais velha que isso
MAX_VISTAS = 800             # tamanho máximo do histórico de notícias já postadas

# (nome, consulta, idioma, país, edição)
FEEDS = [
    ("Rocket League (PT)", "Rocket League", "pt-BR", "BR", "BR:pt-419"),
    ("RLCS (PT)", "RLCS", "pt-BR", "BR", "BR:pt-419"),
    ("Rocket League (EN)", "Rocket League", "en-US", "US", "US:en"),
]

# A notícia só é postada se o título mencionar um destes termos (evita ruído)
PALAVRAS_OBRIGATORIAS = ("rocket league", "rlcs", "psyonix")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TryHardersBot/1.0)"}
COR_EMBED = 0x1F8B4C


def _url_feed(consulta: str, idioma: str, pais: str, edicao: str) -> str:
    q = quote(f"{consulta} when:{MAX_IDADE_DIAS}d")
    return f"https://news.google.com/rss/search?q={q}&hl={idioma}&gl={pais}&ceid={edicao}"


def _normalizar_titulo(titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def _id_noticia(titulo: str) -> str:
    return hashlib.md5(_normalizar_titulo(titulo)[:80].encode("utf-8")).hexdigest()[:14]


def parsear_feed(xml_texto: str) -> list[dict]:
    """Converte o XML do RSS em uma lista de notícias:
    {"id", "titulo", "fonte", "link", "data" (datetime UTC)}.
    Itens sem título/link/data válida, velhos demais ou fora do assunto são
    descartados."""
    try:
        raiz = ET.fromstring(xml_texto)
    except ET.ParseError:
        return []

    limite = datetime.now(timezone.utc) - timedelta(days=MAX_IDADE_DIAS)
    noticias = []

    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        data_txt = (item.findtext("pubDate") or "").strip()
        fonte_el = item.find("source")
        fonte = (fonte_el.text or "").strip() if fonte_el is not None else ""

        if not titulo or not link.startswith("http") or not data_txt:
            continue

        try:
            data = parsedate_to_datetime(data_txt)
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
            data = data.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if data < limite:
            continue

        # O Google Notícias coloca " - Fonte" no fim do título: tira daí
        if fonte and titulo.endswith(f" - {fonte}"):
            titulo = titulo[: -len(f" - {fonte}")].rstrip()
        elif " - " in titulo and not fonte:
            titulo, _, fonte = titulo.rpartition(" - ")

        titulo_baixo = titulo.lower()
        if not any(p in titulo_baixo for p in PALAVRAS_OBRIGATORIAS):
            continue

        noticias.append({
            "id": _id_noticia(titulo),
            "titulo": titulo,
            "fonte": fonte or "Fonte desconhecida",
            "link": link,
            "data": data,
        })

    return noticias


def _montar_embed(n: dict) -> discord.Embed:
    embed = discord.Embed(
        title=n["titulo"][:256],
        url=n["link"],
        description=f"📰 **{n['fonte']}** • <t:{int(n['data'].timestamp())}:R>",
        color=COR_EMBED,
    )
    embed.set_footer(text="Notícias de Rocket League")
    return embed


class Noticias(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self.buscar_noticias.start()

    def cog_unload(self):
        self.buscar_noticias.cancel()

    # ── busca ───────────────────────────────────────────────────────────
    async def _baixar(self, sessao: aiohttp.ClientSession, url: str) -> str | None:
        try:
            async with sessao.get(url) as resp:
                if resp.status != 200:
                    print(f"[NOTICIAS] ⚠️ Feed devolveu HTTP {resp.status}: {url}")
                    return None
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"[NOTICIAS] ⚠️ Falha ao baixar feed: {e}")
            return None

    async def _coletar(self) -> list[dict]:
        """Baixa todos os feeds e devolve as notícias sem títulos repetidos,
        da mais antiga pra mais nova."""
        por_id: dict[str, dict] = {}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as sessao:
            for nome, consulta, idioma, pais, edicao in FEEDS:
                xml_texto = await self._baixar(sessao, _url_feed(consulta, idioma, pais, edicao))
                if not xml_texto:
                    continue
                for n in parsear_feed(xml_texto):
                    por_id.setdefault(n["id"], n)
        return sorted(por_id.values(), key=lambda n: n["data"])

    # ── rodada ──────────────────────────────────────────────────────────
    async def _obter_canal(self, config: dict):
        canal_id = config.get("canal_id") or CANAL_NOTICIAS_ID
        if not canal_id:
            return None
        canal = self.bot.get_channel(canal_id)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(canal_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                print(f"[NOTICIAS] ⚠️ Canal {canal_id} inacessível: {e}")
                return None
        return canal

    async def _rodada(self) -> int:
        """Procura notícias novas e posta. Devolve quantas foram postadas."""
        async with self._lock:
            config = ler_json(CONFIG_PATH, dict)
            if not config.get("ativo", True):
                return 0

            canal = await self._obter_canal(config)
            if canal is None:
                return 0

            vistas: list[str] = config.get("vistas", [])
            vistas_set = set(vistas)
            novas = [n for n in await self._coletar() if n["id"] not in vistas_set]
            if not novas:
                return 0

            if not config.get("iniciado"):
                # 1ª rodada: posta só as mais recentes e marca todas como vistas
                a_postar = novas[-PRIMEIRA_RODADA_QTD:]
                vistas.extend(n["id"] for n in novas if n not in a_postar)
                config["iniciado"] = True
            else:
                a_postar = novas[:MAX_POR_RODADA]  # mais antigas primeiro

            postadas = 0
            for n in a_postar:
                try:
                    await canal.send(embed=_montar_embed(n))
                except discord.HTTPException as e:
                    print(f"[NOTICIAS] ⚠️ Erro ao postar notícia: {e}")
                    break
                vistas.append(n["id"])
                postadas += 1

            config["vistas"] = vistas[-MAX_VISTAS:]
            salvar_json(CONFIG_PATH, config)
            if postadas:
                print(f"[NOTICIAS] 📰 {postadas} notícia(s) postada(s).")
            return postadas

    @tasks.loop(minutes=INTERVALO_MINUTOS)
    async def buscar_noticias(self):
        try:
            await self._rodada()
        except Exception as e:
            # uma falha pontual não pode matar o loop pro resto da vida do processo
            print(f"[NOTICIAS] ⚠️ Erro na rodada de notícias: {e}")

    @buscar_noticias.before_loop
    async def antes_buscar(self):
        await self.bot.wait_until_ready()

    # ── comandos de administração ───────────────────────────────────────
    @app_commands.command(name="noticias_canal", description="[Staff] Define o canal onde o bot posta as notícias.")
    @app_commands.describe(canal="Canal que vai receber as notícias")
    @app_commands.checks.has_permissions(administrator=True)
    async def noticias_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        config = ler_json(CONFIG_PATH, dict)
        config["canal_id"] = canal.id
        salvar_json(CONFIG_PATH, config)
        await interaction.response.send_message(
            f"✅ Notícias de Rocket League agora serão postadas em {canal.mention} "
            f"(procuro novidades a cada {INTERVALO_MINUTOS} min).",
            ephemeral=True,
        )

    @app_commands.command(name="noticias_agora", description="[Staff] Procura e posta notícias novas agora.")
    @app_commands.checks.has_permissions(administrator=True)
    async def noticias_agora(self, interaction: discord.Interaction):
        config = ler_json(CONFIG_PATH, dict)
        if not (config.get("canal_id") or CANAL_NOTICIAS_ID):
            await interaction.response.send_message(
                "⚠️ Nenhum canal configurado ainda. Use `/noticias_canal` primeiro.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        postadas = await self._rodada()
        if postadas:
            await interaction.followup.send(f"✅ {postadas} notícia(s) postada(s).", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ Nenhuma notícia nova no momento.", ephemeral=True)

    @app_commands.command(name="noticias_toggle", description="[Staff] Liga ou desliga as notícias automáticas.")
    @app_commands.checks.has_permissions(administrator=True)
    async def noticias_toggle(self, interaction: discord.Interaction):
        config = ler_json(CONFIG_PATH, dict)
        config["ativo"] = not config.get("ativo", True)
        salvar_json(CONFIG_PATH, config)
        estado = "🟢 ativadas" if config["ativo"] else "🔴 desativadas"
        await interaction.response.send_message(f"Notícias automáticas {estado}.", ephemeral=True)

    @noticias_canal.error
    @noticias_agora.error
    @noticias_toggle.error
    async def _erro_comandos(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar esse comando.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Noticias(bot))
