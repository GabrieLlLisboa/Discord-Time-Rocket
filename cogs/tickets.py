import asyncio
import html
import io
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from discord import app_commands

from cogs import mod_utils as mu
from cogs.json_store import ler_json, salvar_json

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


FUSO_BRASILIA = timezone(timedelta(hours=-3))


ARQ_CONFIG      = "data/ticket_config.json"
ARQ_AVALIACOES  = "data/ticket_avaliacoes.json"
ARQ_TEMPOS      = "data/ticket_tempos.json"
ARQ_ABERTOS     = "data/ticket_abertos.json"
ARQ_EXCLUSOES_PENDENTES = "data/ticket_exclusoes_pendentes.json"

# tempo máximo esperando o dono avaliar antes de deletar o canal de qualquer jeito
TIMEOUT_ESPERA_AVALIACAO_SEGUNDOS = 600


def _ler_config() -> dict:
    return ler_json(ARQ_CONFIG, dict)


def _salvar_config(dados: dict):
    salvar_json(ARQ_CONFIG, dados)


def _ler_avaliacoes() -> dict:
    return ler_json(ARQ_AVALIACOES, lambda: {"total": 0, "soma": 0, "notas": {}})


def _salvar_avaliacoes(dados: dict):
    salvar_json(ARQ_AVALIACOES, dados)


def _ler_tempos() -> dict:
    return ler_json(ARQ_TEMPOS, lambda: {"total": 0, "soma_segundos": 0})


def _salvar_tempos(dados: dict):
    salvar_json(ARQ_TEMPOS, dados)


def _ler_abertos() -> dict:
    return ler_json(ARQ_ABERTOS, dict)


def _salvar_abertos(dados: dict):
    salvar_json(ARQ_ABERTOS, dados)


def _ler_exclusoes_pendentes() -> dict:
    return ler_json(ARQ_EXCLUSOES_PENDENTES, dict)


def _salvar_exclusoes_pendentes(dados: dict):
    salvar_json(ARQ_EXCLUSOES_PENDENTES, dados)


COOLDOWN_SEGUNDOS       = 60
MAX_TICKETS_SIMULTANEOS = 3
_ultima_criacao: dict[int, float] = {}

CATEGORIAS = [
    discord.SelectOption(
        label="Dúvidas",
        description="Tem alguma dúvida? Fale com a equipe.",
        emoji="❓",
        value="duvidas"
    ),
    discord.SelectOption(
        label="Denúncias",
        description="Reporte um jogador ou situação.",
        emoji="🚨",
        value="denuncias"
    ),
    discord.SelectOption(
        label="Mais sobre o time",
        description="Quer saber mais sobre nossa equipe?",
        emoji="🏆",
        value="time"
    ),
    discord.SelectOption(
        label="Problemas Técnicos",
        description="Encontrou algum bug ou erro?",
        emoji="🔧",
        value="tecnico"
    ),
    discord.SelectOption(
        label="Desenvolvimento",
        description="Assunto interno da equipe de desenvolvimento.",
        emoji="💻",
        value="dev"
    ),
    discord.SelectOption(
        label="Tratativas com Administração",
        description="Assunto restrito — visível apenas para administradores.",
        emoji="🛡️",
        value="administracao"
    ),
]

NOMES = {
    "duvidas":       "duvida",
    "denuncias":     "denuncia",
    "time":          "time",
    "tecnico":       "tecnico",
    "dev":           "dev",
    "administracao": "administracao",
}

CORES = {
    "duvidas":       0x5865F2,
    "denuncias":     0xED4245,
    "time":          0xFEE75C,
    "tecnico":       0x57F287,
    "dev":           0x9B59B6,
    "administracao": 0x2C2F33,
}


CARGO_DESENVOLVIMENTO_ID = 1525540085112770746

# cargos marcados na abertura de tíquete de desenvolvimento (no lugar do
# cargo de equipe normal)
CARGO_DEV_PING_1 = 1532739361198833874
CARGO_DEV_PING_2 = CARGO_DESENVOLVIMENTO_ID


CARGO_EQUIPE_ID = 1532184563491541164


_FONTES_CANDIDATAS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_FONTES_CANDIDATAS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _carregar_fonte(tamanho: int, negrito: bool = True):
    candidatos = _FONTES_CANDIDATAS if negrito else _FONTES_CANDIDATAS_REGULAR
    for caminho in candidatos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()


def _formatar_duracao(segundos: float) -> str:
    segundos = max(0, int(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos}min"
    if minutos:
        return f"{minutos}min {seg}s"
    return f"{seg}s"


def gerar_imagem_tempo_resposta(media_segundos: float | None, total: int) -> discord.File | None:
    """Gera um cartão PNG com o tempo médio de resposta da equipe, pra ser
    anexado na embed de abertura de cada novo tíquete."""
    if not _PIL_OK:
        return None

    try:
        largura, altura = 600, 150
        fundo    = (43, 45, 49)
        destaque = (88, 101, 242)
        texto_cor   = (219, 222, 225)
        texto_claro = (148, 155, 164)

        img = Image.new("RGB", (largura, altura), fundo)
        draw = ImageDraw.Draw(img)


        draw.rectangle([0, 0, 8, altura], fill=destaque)

        fonte_titulo = _carregar_fonte(20, negrito=True)
        fonte_valor  = _carregar_fonte(40, negrito=True)
        fonte_sub    = _carregar_fonte(15, negrito=False)

        draw.text((32, 20), "TEMPO MÉDIO DE RESPOSTA DA EQUIPE", font=fonte_titulo, fill=texto_claro)

        valor_texto = _formatar_duracao(media_segundos) if media_segundos is not None else "Sem dados ainda"
        draw.text((32, 54), valor_texto, font=fonte_valor, fill=destaque)

        sub_texto = (
            f"Baseado em {total} atendimento(s)" if total > 0
            else "Ainda não há atendimentos suficientes"
        )
        draw.text((32, 112), sub_texto, font=fonte_sub, fill=texto_claro)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="tempo_resposta.png")
    except Exception as e:
        print(f"[TICKET] ⚠️ Erro ao gerar imagem de tempo médio de resposta: {e}")
        return None


async def gerar_transcript_html(canal: discord.TextChannel) -> discord.File:
    mensagens = [m async for m in canal.history(limit=None, oldest_first=True)]

    blocos = []
    for m in mensagens:
        hora = m.created_at.astimezone(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")
        autor = html.escape(str(m.author))
        avatar = m.author.display_avatar.url
        conteudo = html.escape(m.content or "").replace("\n", "<br>")

        anexos = "".join(
            f'<div class="anexo">📎 <a href="{html.escape(a.url)}" target="_blank">{html.escape(a.filename)}</a></div>'
            for a in m.attachments
        )

        embeds_txt = ""
        for e in m.embeds:
            partes = []
            if e.title:
                partes.append(f"<strong>{html.escape(e.title)}</strong>")
            if e.description:
                partes.append(html.escape(e.description).replace("\n", "<br>"))
            if partes:
                embeds_txt += f'<div class="embed-box">{"<br>".join(partes)}</div>'

        blocos.append(f"""
        <div class="msg">
          <img class="avatar" src="{avatar}" onerror="this.style.display='none'">
          <div class="conteudo">
            <div class="cabecalho"><span class="autor">{autor}</span><span class="hora">{hora}</span></div>
            <div class="texto">{conteudo}</div>
            {embeds_txt}
            {anexos}
          </div>
        </div>
        """)

    corpo = "\n".join(blocos) if blocos else "<p class='vazio'>Nenhuma mensagem encontrada neste tíquete.</p>"

    doc = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Transcrição — #{html.escape(canal.name)}</title>
<style>
  body {{ background:#313338; color:#dbdee1; font-family: Helvetica, Arial, sans-serif; margin:0; padding:24px; }}
  h1 {{ color:#fff; margin-bottom:4px; }}
  .info {{ color:#949ba4; margin-bottom:20px; }}
  .msg {{ display:flex; gap:14px; margin-bottom:18px; }}
  .avatar {{ width:40px; height:40px; border-radius:50%; flex-shrink:0; }}
  .cabecalho {{ margin-bottom:2px; }}
  .autor {{ font-weight:700; color:#fff; }}
  .hora {{ font-size:12px; color:#949ba4; margin-left:8px; }}
  .texto {{ white-space:pre-wrap; line-height:1.45; word-break:break-word; }}
  .embed-box {{ border-left:4px solid #5865F2; background:#2b2d31; padding:10px 14px; margin-top:6px; border-radius:4px; max-width:520px; }}
  .anexo {{ margin-top:6px; }}
  .anexo a {{ color:#00a8fc; text-decoration:none; }}
  .vazio {{ color:#949ba4; font-style:italic; }}
  hr {{ border-color:#3f4147; margin-bottom:20px; }}
</style>
</head>
<body>
<h1>📄 Transcrição — #{html.escape(canal.name)}</h1>
<p class="info">Gerado em {datetime.now(FUSO_BRASILIA).strftime('%d/%m/%Y %H:%M')} — {len(mensagens)} mensagem(ns)</p>
<hr>
{corpo}
</body>
</html>"""

    buffer = io.BytesIO(doc.encode("utf-8"))
    return discord.File(buffer, filename=f"transcript-{canal.name}.html")


def _montar_view_avaliacao(dono_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for nota in range(1, 6):
        view.add_item(discord.ui.Button(
            label="⭐" * nota,
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_avaliacao_{nota}_{dono_id}",
        ))
    return view


async def criar_ticket(interaction: discord.Interaction, valor: str):
    guild     = interaction.guild
    membro    = interaction.user


    agora  = time.monotonic()
    ultima = _ultima_criacao.get(membro.id)
    if ultima is not None and (agora - ultima) < COOLDOWN_SEGUNDOS:
        restante = int(COOLDOWN_SEGUNDOS - (agora - ultima)) + 1
        await interaction.response.send_message(
            f"⏳ Aguarde `{restante}s` antes de abrir outro tíquete.",
            ephemeral=True
        )
        return


    nome_canal = f"ticket-{NOMES[valor]}-{membro.id}"


    existente = discord.utils.get(guild.text_channels, name=nome_canal)
    if existente:
        await interaction.response.send_message(
            f"⚠️ Você já tem um tíquete aberto: {existente.mention}",
            ephemeral=True
        )
        return


    abertos = [
        c for c in guild.text_channels
        if c.name.startswith("ticket-") and c.name.endswith(f"-{membro.id}")
    ]
    if len(abertos) >= MAX_TICKETS_SIMULTANEOS:
        await interaction.response.send_message(
            f"⚠️ Você já possui `{len(abertos)}` tíquete(s) aberto(s) "
            f"(limite: `{MAX_TICKETS_SIMULTANEOS}`). Feche algum antes de abrir outro.",
            ephemeral=True
        )
        return


    _ultima_criacao[membro.id] = agora


    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        membro:             discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    if valor == "dev":


        cargo_dev = guild.get_role(CARGO_DESENVOLVIMENTO_ID)
        if cargo_dev is not None:
            overwrites[cargo_dev] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            print(f"[TICKET] ⚠️ Cargo de Desenvolvimento ({CARGO_DESENVOLVIMENTO_ID}) não encontrado no servidor.")

        cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
        if cargo_equipe is not None:
            overwrites[cargo_equipe] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    elif valor == "administracao":


        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    else:

        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
        if cargo_equipe is not None:
            overwrites[cargo_equipe] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            print(f"[TICKET] ⚠️ Cargo da equipe ({CARGO_EQUIPE_ID}) não encontrado no servidor.")


    canal = await guild.create_text_channel(
        name=nome_canal,
        overwrites=overwrites,
        reason=f"Tíquete aberto por {membro} — {valor}"
    )


    registro_abertos = _ler_abertos()
    registro_abertos[str(canal.id)] = {"criado_em": time.time(), "respondido": False}
    _salvar_abertos(registro_abertos)


    rotulo = next((o.label for o in CATEGORIAS if o.value == valor), valor)
    embed = discord.Embed(
        title=f"Tíquete — {rotulo}",
        description=(
            f"Olá, {membro.mention}! 👋\n\n"
            f"A equipe irá te atender em breve.\n"
            f"Descreva seu problema ou dúvida abaixo."
        ),
        color=CORES[valor]
    )
    embed.set_footer(text="Pra fechar este tíquete, clique no botão abaixo.")
    embed.set_thumbnail(url=membro.display_avatar.url)


    tempos = _ler_tempos()
    total_t = tempos.get("total", 0)
    media_t = (tempos.get("soma_segundos", 0) / total_t) if total_t > 0 else None
    arquivo_imagem = gerar_imagem_tempo_resposta(media_t, total_t)
    if arquivo_imagem:
        embed.set_image(url="attachment://tempo_resposta.png")


    view = FecharTicketView()
    conteudo = membro.mention
    if valor == "dev":
        # ticket de dev não marca o cargo de equipe, marca só esses dois
        # cargos específicos de desenvolvimento
        conteudo = f"{membro.mention} <@&{CARGO_DEV_PING_1}> <@&{CARGO_DEV_PING_2}>"
    elif valor != "administracao" and guild.get_role(CARGO_EQUIPE_ID) is not None:
        conteudo = f"{membro.mention} <@&{CARGO_EQUIPE_ID}>"

    if arquivo_imagem:
        await canal.send(content=conteudo, embed=embed, view=view, file=arquivo_imagem)
    else:
        await canal.send(content=conteudo, embed=embed, view=view)

    await interaction.response.send_message(
        f"✅ Tíquete aberto! Acesse: {canal.mention}",
        ephemeral=True
    )
    print(f"[TICKET] ✅ Canal {nome_canal} criado para {membro}.")


class TicketSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            custom_id="ticket_select",
            placeholder="📂 Selecione o tipo de suporte...",
            min_values=1,
            max_values=1,
            options=CATEGORIAS,
        )

    async def callback(self, interaction: discord.Interaction):
        await criar_ticket(interaction, self.values[0])


class AbrirTicketDevView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📂 Abrir Tíquete de Desenvolvimento", style=discord.ButtonStyle.primary, custom_id="abrir_ticket_dev")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await criar_ticket(interaction, "dev")


class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🙋 Assumir Tíquete", style=discord.ButtonStyle.primary, custom_id="assumir_ticket", row=0)
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.assumir_ticket(interaction)

    @discord.ui.button(label="🔒 Fechar Tíquete", style=discord.ButtonStyle.danger, custom_id="fechar_ticket", row=0)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):


        pode_fechar = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_fechar and interaction.channel.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_fechar = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)


        if interaction.channel.name.startswith(f"ticket-{NOMES['administracao']}-"):
            pode_fechar = (
                interaction.user.guild_permissions.administrator
                or mu.eh_super_admin(interaction.user.id)
            )

        if not pode_fechar:
            await interaction.response.send_message(
                "❌ Você não tem permissão para fechar este tíquete.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Como você quer encerrar esse tíquete?",
            view=EscolhaFecharView(),
            ephemeral=True,
        )


class ReabrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔓 Reabrir Tíquete", style=discord.ButtonStyle.success, custom_id="reabrir_ticket")
    async def reabrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel


        pode_reabrir = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_reabrir and canal.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_reabrir = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)


        if canal.name.startswith(f"ticket-{NOMES['administracao']}-"):
            pode_reabrir = (
                interaction.user.guild_permissions.administrator
                or mu.eh_super_admin(interaction.user.id)
            )

        if not pode_reabrir:
            await interaction.response.send_message(
                "❌ Você não tem permissão para reabrir este tíquete.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.reabrir_ticket(interaction)


class ForcarExclusaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⏭️ Forçar exclusão (sem esperar avaliação)", style=discord.ButtonStyle.danger, custom_id="ticket_forcar_exclusao")
    async def forcar(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel

        pode_forcar = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_forcar and canal.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_forcar = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)

        if canal.name.startswith(f"ticket-{NOMES['administracao']}-"):
            pode_forcar = (
                interaction.user.guild_permissions.administrator
                or mu.eh_super_admin(interaction.user.id)
            )

        if not pode_forcar:
            await interaction.response.send_message(
                "❌ Você não tem permissão pra forçar a exclusão deste tíquete.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("🗑️ Ok, deletando sem esperar a avaliação...", ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog._deletar_de_fato(canal, motivo=f"exclusão forçada por {interaction.user} (sem avaliação)")


class EscolhaFecharView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🔒 Fechar (não deletar)", style=discord.ButtonStyle.secondary, custom_id="ticket_fechar_manter")
    async def manter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🔒 Fechando o tíquete...", view=None)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.finalizar_ticket(interaction, deletar=False)

    @discord.ui.button(label="🗑️ Deletar", style=discord.ButtonStyle.danger, custom_id="ticket_fechar_deletar")
    async def deletar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🗑️ Deletando o tíquete...", view=None)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.finalizar_ticket(interaction, deletar=True)


class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @staticmethod
    def _extrair_dono_id(nome_canal: str) -> int | None:
        if not nome_canal.startswith("ticket-"):
            return None
        try:
            return int(nome_canal.rsplit("-", 1)[-1])
        except ValueError:
            return None

    @staticmethod
    def _remover_ticket_aberto(canal_id: int):
        abertos = _ler_abertos()
        if str(canal_id) in abertos:
            del abertos[str(canal_id)]
            _salvar_abertos(abertos)


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        canal = message.channel
        if not isinstance(canal, discord.TextChannel) or not canal.name.startswith("ticket-"):
            return

        dono_id = self._extrair_dono_id(canal.name)

        abertos = _ler_abertos()
        info = abertos.get(str(canal.id))

        assumido_por = info.get("assumido_por") if info else None
        if assumido_por and message.author.id not in (dono_id, assumido_por):
            # ticket assumido por alguém: só o dono do tíquete e quem assumiu
            # podem falar aqui — mesmo admin sendo admin, a permissão de canal
            # não segura ele, então apaga a msg na unha
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            try:
                responsavel = message.guild.get_member(assumido_por)
                nome = responsavel.mention if responsavel else f"<@{assumido_por}>"
                aviso = await canal.send(
                    f"⚠️ {message.author.mention}, esse tíquete já foi assumido por {nome}. "
                    f"Só ele (ou um admin, clicando em **Assumir Tíquete** de novo) pode responder aqui.",
                    delete_after=8,
                )
            except discord.HTTPException:
                pass
            return

        if dono_id is None or message.author.id == dono_id:
            return

        if info is None or info.get("respondido"):
            return

        criado_em = info.get("criado_em")
        if not criado_em:
            return

        delta = time.time() - criado_em
        if delta < 0:
            return

        tempos = _ler_tempos()
        tempos["total"] = tempos.get("total", 0) + 1
        tempos["soma_segundos"] = tempos.get("soma_segundos", 0) + delta
        _salvar_tempos(tempos)

        info["respondido"] = True
        abertos[str(canal.id)] = info
        _salvar_abertos(abertos)

        await self.atualizar_embed_tempo(message.guild)


    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = (interaction.data or {}).get("custom_id", "")
        if not custom_id.startswith("ticket_avaliacao_"):
            return

        partes = custom_id.split("_")
        try:
            nota = int(partes[2])
            dono_id = int(partes[3])
        except (IndexError, ValueError):
            return

        if interaction.user.id != dono_id:
            await interaction.response.send_message(
                "❌ Só quem abriu o tíquete pode avaliar o atendimento.",
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.description = f"✅ Obrigado pela avaliação! Você deu **{'⭐' * nota}** ({nota}/5)."
        embed.color = 0x57F287

        await interaction.response.edit_message(embed=embed, view=None)
        await self.registrar_avaliacao(interaction.guild, nota)

        pendentes = _ler_exclusoes_pendentes()
        if str(interaction.channel.id) in pendentes:
            try:
                await interaction.channel.send("🗑️ Valeu pela avaliação! Deletando o tíquete agora...")
            except discord.HTTPException:
                pass
            await self._deletar_de_fato(interaction.channel, motivo="avaliação registrada")


    async def registrar_avaliacao(self, guild: discord.Guild, nota: int):
        dados = _ler_avaliacoes()
        dados["total"] = dados.get("total", 0) + 1
        dados["soma"] = dados.get("soma", 0) + nota
        notas = dados.setdefault("notas", {})
        chave = str(nota)
        notas[chave] = notas.get(chave, 0) + 1
        _salvar_avaliacoes(dados)
        print(f"[TICKET] ⭐ Avaliação registrada: {nota}/5 (total: {dados['total']}).")
        await self.atualizar_embed_media(guild)

    async def atualizar_embed_media(self, guild: discord.Guild):
        cfg = _ler_config()
        canal_id = cfg.get("setup_channel_id")
        if not canal_id:
            return

        canal = guild.get_channel(canal_id) or self.bot.get_channel(canal_id)
        if canal is None:
            return

        dados = _ler_avaliacoes()
        total = dados.get("total", 0)
        soma = dados.get("soma", 0)
        media = (soma / total) if total > 0 else 0.0

        embed = discord.Embed(
            title="⭐ Avaliação média dos atendimentos",
            description=(
                f"**{media:.1f} / 5.0** ⭐ — baseado em {total} avaliação(ões)"
                if total > 0 else
                "Ainda não temos avaliações registradas."
            ),
            color=0xFEE75C,
        )
        if total > 0:
            notas = dados.get("notas", {})
            distrib = "\n".join(
                f"{'⭐' * int(n)} — {notas.get(n, 0)}"
                for n in ["5", "4", "3", "2", "1"]
            )
            embed.add_field(name="Distribuição", value=distrib, inline=False)
        embed.set_footer(text="Atualizado automaticamente a cada nova avaliação.")

        mensagem = None
        media_msg_id = cfg.get("media_message_id")
        if media_msg_id:
            try:
                mensagem = await canal.fetch_message(media_msg_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem = None

        if mensagem:
            try:
                await mensagem.edit(embed=embed)
                return
            except discord.HTTPException:
                pass

        try:
            nova = await canal.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[TICKET] ⚠️ Não consegui mandar a embed de avaliação média: {e}")
            return

        cfg["media_message_id"] = nova.id
        cfg["setup_channel_id"] = canal.id
        _salvar_config(cfg)


    async def atualizar_embed_tempo(self, guild: discord.Guild):
        cfg = _ler_config()
        canal_id = cfg.get("setup_channel_id")
        if not canal_id:
            return

        canal = guild.get_channel(canal_id) or self.bot.get_channel(canal_id)
        if canal is None:
            return

        tempos = _ler_tempos()
        total = tempos.get("total", 0)
        soma = tempos.get("soma_segundos", 0)
        media = (soma / total) if total > 0 else None

        embed = discord.Embed(
            title="⏱️ Tempo médio de resposta da equipe",
            description=(
                f"**{_formatar_duracao(media)}** — baseado em {total} atendimento(s)"
                if total > 0 else
                "Ainda não temos atendimentos suficientes pra calcular a média."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Atualizado automaticamente sempre que a equipe responde um tíquete pela primeira vez.")

        mensagem = None
        tempo_msg_id = cfg.get("tempo_message_id")
        if tempo_msg_id:
            try:
                mensagem = await canal.fetch_message(tempo_msg_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem = None

        if mensagem:
            try:
                await mensagem.edit(embed=embed)
                return
            except discord.HTTPException:
                pass

        try:
            nova = await canal.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[TICKET] ⚠️ Não consegui mandar a embed de tempo médio de resposta: {e}")
            return

        cfg["tempo_message_id"] = nova.id
        cfg["setup_channel_id"] = canal.id
        _salvar_config(cfg)


    async def finalizar_ticket(self, interaction: discord.Interaction, deletar: bool):
        canal = interaction.channel
        guild = interaction.guild

        dono_id = self._extrair_dono_id(canal.name)
        dono = guild.get_member(dono_id) if dono_id else None
        if dono is None and dono_id:
            try:
                dono = await self.bot.fetch_user(dono_id)
            except discord.HTTPException:
                dono = None


        arquivo_transcript = None
        try:
            arquivo_transcript = await gerar_transcript_html(canal)
        except Exception as e:
            print(f"[TICKET] ⚠️ Erro ao gerar transcript de #{canal.name}: {e}")


        if dono_id:
            embed_avaliacao = discord.Embed(
                title="⭐ Avalie o atendimento",
                description=(
                    f"{dono.mention if dono else 'Você'}, como foi o atendimento que você recebeu nesse tíquete?\n"
                    "Clica numa das opções abaixo pra avaliar:"
                ),
                color=0xFEE75C,
            )
            try:
                await canal.send(embed=embed_avaliacao, view=_montar_view_avaliacao(dono_id))
            except discord.HTTPException:
                pass


        if dono and arquivo_transcript:
            try:
                embed_dm = discord.Embed(
                    title="📄 Transcrição do seu tíquete",
                    description=(
                        f"Segue em anexo a transcrição completa do tíquete **#{canal.name}**.\n"
                        "Se ainda não avaliou o atendimento, dá uma olhada no canal do tíquete."
                    ),
                    color=0x5865F2,
                )
                await dono.send(embed=embed_dm, file=arquivo_transcript)
            except discord.Forbidden:
                print(f"[TICKET] ⚠️ Não consegui mandar DM pra {dono} (DMs fechadas).")
            except discord.HTTPException as e:
                print(f"[TICKET] ⚠️ Erro ao mandar transcript por DM: {e}")

        self._remover_ticket_aberto(canal.id)

        if deletar:
            if dono_id:
                pendentes = _ler_exclusoes_pendentes()
                pendentes[str(canal.id)] = {
                    "dono_id": dono_id,
                    "guild_id": guild.id,
                    "solicitado_por": interaction.user.id,
                    "criado_em": time.time(),
                }
                _salvar_exclusoes_pendentes(pendentes)

                try:
                    await canal.send(
                        f"🗑️ Esse tíquete vai ser **deletado automaticamente assim que "
                        f"{dono.mention if dono else 'o dono'} avaliar o atendimento** ali em cima "
                        f"(ou em até {TIMEOUT_ESPERA_AVALIACAO_SEGUNDOS // 60} minutos, o que vier primeiro).",
                        view=ForcarExclusaoView(),
                    )
                except discord.HTTPException:
                    pass
                try:
                    await interaction.followup.send(
                        "🗑️ Vou esperar a avaliação antes de deletar (ou forçar depois se precisar).",
                        ephemeral=True
                    )
                except discord.HTTPException:
                    pass

                asyncio.create_task(self._aguardar_avaliacao_e_deletar(canal.id))
                print(f"[TICKET] ⏳ Canal {canal.name} aguardando avaliação antes de deletar (pedido por {interaction.user}).")
            else:

                try:
                    await canal.send("🗑️ Este tíquete será **deletado** em instantes. A transcrição foi enviada na sua DM.")
                except discord.HTTPException:
                    pass
                try:
                    await interaction.followup.send("🗑️ Tíquete será deletado em alguns segundos...", ephemeral=True)
                except discord.HTTPException:
                    pass
                await self._deletar_de_fato(canal, motivo=f"tíquete deletado por {interaction.user} (sem dono identificável)")
        else:
            try:
                if dono:
                    await canal.set_permissions(dono, view_channel=True, send_messages=False)
            except discord.Forbidden:
                pass
            try:
                await canal.send(
                    "🔒 Este tíquete foi **fechado** (canal mantido para consulta). "
                    "A transcrição foi enviada na sua DM.\n"
                    "Se precisar continuar o atendimento, clique em **Reabrir Tíquete** abaixo.",
                    view=ReabrirTicketView(),
                )
            except discord.HTTPException:
                pass
            try:
                await interaction.followup.send("🔒 Tíquete fechado (canal mantido).", ephemeral=True)
            except discord.HTTPException:
                pass
            print(f"[TICKET] 🔒 Canal {canal.name} fechado (não deletado) por {interaction.user}.")


    async def _deletar_de_fato(self, canal: discord.TextChannel, motivo: str):
        pendentes = _ler_exclusoes_pendentes()
        if str(canal.id) in pendentes:
            del pendentes[str(canal.id)]
            _salvar_exclusoes_pendentes(pendentes)

        try:
            await canal.delete(reason=motivo)
            print(f"[TICKET] 🗑️ Canal {canal.name} deletado ({motivo}).")
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            print(f"[TICKET] ⚠️ Erro ao deletar canal {canal.name}: {e}")

    async def _aguardar_avaliacao_e_deletar(self, canal_id: int):
        """Se o dono não avaliar em TIMEOUT_ESPERA_AVALIACAO_SEGUNDOS, deleta
        o canal de qualquer jeito (senão o tíquete ficaria aberto pra sempre
        caso o dono nunca clique em avaliar)."""
        await asyncio.sleep(TIMEOUT_ESPERA_AVALIACAO_SEGUNDOS)

        pendentes = _ler_exclusoes_pendentes()
        if str(canal_id) not in pendentes:

            return

        canal = self.bot.get_channel(canal_id)
        if canal is None:
            del pendentes[str(canal_id)]
            _salvar_exclusoes_pendentes(pendentes)
            return

        try:
            await canal.send("⏳ Ninguém avaliou o atendimento a tempo, deletando o tíquete agora.")
        except discord.HTTPException:
            pass

        await self._deletar_de_fato(canal, motivo="timeout esperando avaliação")


    async def assumir_ticket(self, interaction: discord.Interaction):
        canal = interaction.channel
        guild = interaction.guild

        pode_assumir = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_assumir and canal.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_assumir = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)

        if canal.name.startswith(f"ticket-{NOMES['administracao']}-"):
            pode_assumir = (
                interaction.user.guild_permissions.administrator
                or mu.eh_super_admin(interaction.user.id)
            )

        if not pode_assumir:
            await interaction.response.send_message(
                "❌ Você não tem permissão para assumir este tíquete.",
                ephemeral=True
            )
            return

        abertos = _ler_abertos()
        info = abertos.get(str(canal.id), {})
        assumido_por = info.get("assumido_por")

        if assumido_por and assumido_por != interaction.user.id:
            responsavel = guild.get_member(assumido_por)
            nome = responsavel.mention if responsavel else f"<@{assumido_por}>"
            eh_admin = interaction.user.guild_permissions.administrator or mu.eh_super_admin(interaction.user.id)
            if not eh_admin:
                await interaction.response.send_message(
                    f"⚠️ Esse tíquete já foi assumido por {nome}. Só um administrador pode passar pra outra pessoa.",
                    ephemeral=True
                )
                return

        if assumido_por == interaction.user.id:

            cargos_bloqueados = info.get("cargos_bloqueados", [])
            for cargo_id in cargos_bloqueados:
                cargo = guild.get_role(cargo_id)
                if cargo is not None:
                    try:
                        await canal.set_permissions(cargo, view_channel=True, send_messages=True)
                    except discord.Forbidden:
                        pass
            try:
                await canal.set_permissions(interaction.user, overwrite=None)
            except discord.Forbidden:
                pass

            info["assumido_por"] = None
            info["cargos_bloqueados"] = []
            abertos[str(canal.id)] = info
            _salvar_abertos(abertos)

            await interaction.response.send_message(
                f"🔓 {interaction.user.mention} liberou o tíquete. A equipe toda pode responder de novo.",
            )
            return


        cargos_bloqueados = []
        for alvo, overwrite in list(canal.overwrites.items()):
            if isinstance(alvo, discord.Role) and overwrite.send_messages:
                try:
                    await canal.set_permissions(alvo, overwrite=discord.PermissionOverwrite(
                        view_channel=True, send_messages=False
                    ))
                    cargos_bloqueados.append(alvo.id)
                except discord.Forbidden:
                    pass

        try:
            await canal.set_permissions(interaction.user, view_channel=True, send_messages=True)
        except discord.Forbidden:
            pass

        info["assumido_por"] = interaction.user.id
        info["cargos_bloqueados"] = cargos_bloqueados
        abertos[str(canal.id)] = info
        _salvar_abertos(abertos)

        await interaction.response.send_message(
            f"🙋 {interaction.user.mention} assumiu esse tíquete. Só ele vai poder responder por aqui agora "
            f"(clica em **Assumir Tíquete** de novo pra liberar)."
        )
        print(f"[TICKET] 🙋 {interaction.user} assumiu o tíquete {canal.name}.")


    async def reabrir_ticket(self, interaction: discord.Interaction):
        canal = interaction.channel
        guild = interaction.guild

        dono_id = self._extrair_dono_id(canal.name)
        dono = guild.get_member(dono_id) if dono_id else None
        if dono is None and dono_id:
            try:
                dono = await self.bot.fetch_user(dono_id)
            except discord.HTTPException:
                dono = None


        if isinstance(dono, discord.Member):
            try:
                await canal.set_permissions(dono, view_channel=True, send_messages=True)
            except discord.Forbidden:
                pass


        registro_abertos = _ler_abertos()
        registro_abertos[str(canal.id)] = {"criado_em": time.time(), "respondido": False}
        _salvar_abertos(registro_abertos)

        pendentes = _ler_exclusoes_pendentes()
        if str(canal.id) in pendentes:
            del pendentes[str(canal.id)]
            _salvar_exclusoes_pendentes(pendentes)


        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            title="🔓 Tíquete Reaberto",
            description=(
                f"Este tíquete foi **reaberto** por {interaction.user.mention}.\n"
                + (f"{dono.mention} já pode enviar mensagens novamente." if dono else "")
            ),
            color=0x57F287,
        )
        try:
            await canal.send(embed=embed, view=FecharTicketView())
        except discord.HTTPException:
            pass

        try:
            await interaction.followup.send("🔓 Tíquete reaberto com sucesso!", ephemeral=True)
        except discord.HTTPException:
            pass

        print(f"[TICKET] 🔓 Canal {canal.name} reaberto por {interaction.user}.")

    @app_commands.command(name="chamado", description="Chama um usuário pra abrir um tíquete de desenvolvimento.")
    @app_commands.describe(user="Quem você quer chamar")
    async def chamado(self, interaction: discord.Interaction, user: discord.Member):
        pode_usar = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin_membro(interaction.user)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
            or any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)
        )
        if not pode_usar:
            await interaction.response.send_message(
                "❌ Você não tem permissão para usar este comando.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            description=(
                f"Olá {user.mention}!\n"
                "Se você ainda não abriu um tíquete na seção de desenvolvimento, eu não posso te ajudar! "
                "Clique no botão abaixo pra abrir um tíquete na seção de desenvolvimento e eu te ajudar no seu problema."
            ),
            color=0x9B59B6
        )
        await interaction.response.send_message(content=user.mention, embed=embed, view=AbrirTicketDevView())

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context):
        """Envia (ou atualiza, se já existir) o painel de abertura de tíquetes no canal atual."""
        embed = discord.Embed(
            title="🎫 Central de Suporte",
            description=(
                "Precisa de ajuda? Selecione uma categoria abaixo\n"
                "e um canal privado será criado para você.\n\n"
                "❓ **Dúvidas** — Perguntas gerais\n"
                "🚨 **Denúncias** — Reporte jogadores\n"
                "🏆 **Mais sobre o time** — Conheça a equipe\n"
                "🔧 **Problemas Técnicos** — Bugs e erros\n"
                "💻 **Desenvolvimento** — Assunto interno da equipe de dev"
            ),
            color=0x2B2D31
        )
        embed.set_footer(text="Apenas você e a equipe verão seu tíquete.")


        cfg = _ler_config()
        mensagem_existente = None
        canal_id_antigo = cfg.get("setup_channel_id")
        msg_id_antigo = cfg.get("setup_message_id")
        if canal_id_antigo and msg_id_antigo:
            canal_antigo = ctx.guild.get_channel(canal_id_antigo)
            if canal_antigo:
                try:
                    mensagem_existente = await canal_antigo.fetch_message(msg_id_antigo)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    mensagem_existente = None

        if mensagem_existente:
            await mensagem_existente.edit(embed=embed, view=TicketSetupView())
            await ctx.send(f"✅ Painel de tíquetes **atualizado** em {mensagem_existente.channel.mention}.", delete_after=6)
            print(f"[TICKET] ✅ Painel de tíquetes atualizado (#{mensagem_existente.channel.name}) por {ctx.author}.")
        else:
            nova = await ctx.send(embed=embed, view=TicketSetupView())
            cfg["setup_channel_id"] = ctx.channel.id
            cfg["setup_message_id"] = nova.id
            _salvar_config(cfg)
            print(f"[TICKET] ✅ Painel de tíquetes enviado em #{ctx.channel.name} por {ctx.author}.")

        await self.atualizar_embed_media(ctx.guild)
        await self.atualizar_embed_tempo(ctx.guild)

    @setup.error
    async def setup_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa ser **Administrador** para usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
