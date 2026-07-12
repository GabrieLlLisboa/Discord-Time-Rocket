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
"""

from __future__ import annotations

import discord
from discord.ext import commands
import httpx

# Canal onde a galera fala português
CANAL_PT_ID = 1511910275618443314

# Canal "pra ingleses" — só quem tem o cargo de idioma Inglês dispara a
# tradução reversa (EN -> PT) a partir daqui
CANAL_EN_ID = 1525864485884137503
CARGO_INGLES_ID = 1525312330831892481


async def _traduzir(texto: str, idioma_destino: str) -> str | None:
    """Traduz `texto` pro idioma `idioma_destino` ('en' ou 'pt').
    Retorna None se der qualquer erro (rede fora do ar, resposta
    inesperada, etc.) — quem chama trata isso simplesmente não
    republicando a mensagem."""
    if not texto or not texto.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": idioma_destino,
                    "dt": "t",
                    "q": texto,
                },
            )
            resp.raise_for_status()
            dados = resp.json()
            # dados[0] é uma lista de segmentos [texto_traduzido, texto_original, ...]
            return "".join(segmento[0] for segmento in dados[0] if segmento[0])
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        print(f"[TRADUTOR] ⚠️ Erro ao traduzir: {e}")
        return None


class Tradutor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            await self._retransmitir(message, destino_id=CANAL_EN_ID, idioma_destino="en", bandeira="🇬🇧")

        elif message.channel.id == CANAL_EN_ID:
            cargos_do_autor = {r.id for r in getattr(message.author, "roles", [])}
            if CARGO_INGLES_ID not in cargos_do_autor:
                return  # só quem tem o cargo de Inglês dispara a tradução reversa
            await self._retransmitir(message, destino_id=CANAL_PT_ID, idioma_destino="pt", bandeira="🇧🇷")

    async def _retransmitir(self, message: discord.Message, destino_id: int, idioma_destino: str, bandeira: str):
        texto = message.content
        if not texto or not texto.strip():
            return  # mensagem só com imagem/anexo/embed — nada de texto pra traduzir

        traduzido = await _traduzir(texto, idioma_destino)
        if not traduzido:
            return

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
