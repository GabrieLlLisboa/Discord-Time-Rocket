import asyncio
import html
import io
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from cogs import mod_utils as mu
from cogs.json_store import ler_json, salvar_json

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ─────────────────────────────────────────────
#  Cog: Tíquetes
#  Arquivo: cogs/tickets.py
#  Comandos: !setup
#  Abre canal privado por categoria
#
#  Além do fluxo básico de abrir/fechar, esse cog também cuida de:
#    • Avaliação do atendimento (1 a 5 estrelas) com média exibida no
#      canal onde o !setup foi enviado.
#    • Transcrição em HTML mandada na DM de quem abriu o tíquete, tanto
#      ao "Fechar" (mantém o canal) quanto ao "Deletar".
#    • Imagem com o tempo médio de resposta, anexada na embed de
#      abertura de cada novo tíquete.
# ─────────────────────────────────────────────

FUSO_BRASILIA = timezone(timedelta(hours=-3))

# ── Arquivos de dados persistentes ──────────────────────────────────────────
ARQ_CONFIG      = "data/ticket_config.json"      # painel do !setup (msg ids)
ARQ_AVALIACOES  = "data/ticket_avaliacoes.json"  # notas de avaliação
ARQ_TEMPOS      = "data/ticket_tempos.json"      # tempo médio de resposta
ARQ_ABERTOS     = "data/ticket_abertos.json"     # tíquetes abertos agora


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


# ── Anti-abuso na criação de tickets ────────────────────────────────────────
# ANTES: não havia cooldown nem limite de tickets simultâneos — qualquer
# usuário podia clicar repetidamente no menu e abrir vários canais em
# sequência (flood de canais, aproximação do limite de canais do servidor,
# rate limit da API do Discord, possível ataque com contas alternativas).
#
# AGORA:
#  - COOLDOWN_SEGUNDOS: tempo mínimo entre duas criações de ticket pelo
#    mesmo usuário. Uma segunda tentativa dentro da janela é rejeitada sem
#    criar canal nenhum (sem erro, só um aviso ephemeral).
#  - MAX_TICKETS_SIMULTANEOS: quantidade máxima de tickets que um mesmo
#    usuário pode manter abertos ao mesmo tempo (somando todas as
#    categorias). Ao atingir o limite, novas criações são bloqueadas até
#    que algum ticket existente seja fechado.
# Os dados ficam em memória (nível de módulo, não por instância de View),
# então valem para qualquer instância da view — inclusive a persistente
# registrada em main.py — enquanto o processo do bot estiver rodando.
COOLDOWN_SEGUNDOS       = 60
MAX_TICKETS_SIMULTANEOS = 3
_ultima_criacao: dict[int, float] = {}  # user_id -> timestamp (time.monotonic())

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
]

NOMES = {
    "duvidas":   "duvida",
    "denuncias": "denuncia",
    "time":      "time",
    "tecnico":   "tecnico",
    "dev":       "dev",
}

CORES = {
    "duvidas":   0x5865F2,
    "denuncias": 0xED4245,
    "time":      0xFEE75C,
    "tecnico":   0x57F287,
    "dev":       0x9B59B6,
}

# Categoria "Desenvolvimento": tíquete restrito — só quem abriu e o cargo
# abaixo enxergam o canal. Diferente das outras categorias, administradores
# NÃO são adicionados automaticamente aqui.
CARGO_DESENVOLVIMENTO_ID = 1525540085112770746

# Cargo da equipe: quem tem esse cargo é considerado "staff" pra tudo
# relacionado a tíquetes — vê todos os tíquetes (inclusive os de
# Desenvolvimento) e pode fechar/deletar qualquer um, igual administrador.
CARGO_EQUIPE_ID = 1532184563491541164


# ── Helpers de tempo médio de resposta (imagem) ─────────────────────────────
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
        fundo    = (43, 45, 49)     # #2B2D31 — mesmo tom dos embeds do Discord
        destaque = (88, 101, 242)   # #5865F2 — blurple
        texto_cor   = (219, 222, 225)
        texto_claro = (148, 155, 164)

        img = Image.new("RGB", (largura, altura), fundo)
        draw = ImageDraw.Draw(img)

        # Barra de destaque na lateral esquerda
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


# ── Helper de transcrição em HTML ───────────────────────────────────────────
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


# ── View de avaliação (1 a 5 estrelas) ──────────────────────────────────────
# Usa custom_id com o ID de quem abriu o tíquete embutido (em vez de guardar
# estado em memória), assim continua funcionando mesmo depois de um restart
# do bot — o clique é tratado via listener bruto (on_interaction) no cog.
def _montar_view_avaliacao(dono_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for nota in range(1, 6):
        view.add_item(discord.ui.Button(
            label="⭐" * nota,
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_avaliacao_{nota}_{dono_id}",
        ))
    return view


# ── Select Menu ────────────────────────────────────────────────────────────────
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
        valor     = self.values[0]
        guild     = interaction.guild
        membro    = interaction.user

        # ── Cooldown por usuário ────────────────────────────────────────
        agora  = time.monotonic()
        ultima = _ultima_criacao.get(membro.id)
        if ultima is not None and (agora - ultima) < COOLDOWN_SEGUNDOS:
            restante = int(COOLDOWN_SEGUNDOS - (agora - ultima)) + 1
            await interaction.response.send_message(
                f"⏳ Aguarde `{restante}s` antes de abrir outro tíquete.",
                ephemeral=True
            )
            return

        # Nome do canal baseado no ID do usuário — não no username.
        # ANTES: usava membro.name, então dois usernames parecidos podiam
        # colidir, um usuário podia mudar de nome e "perder" a associação
        # com o próprio ticket, e dava pra descobrir se outra pessoa tinha
        # ticket aberto só testando nomes parecidos. O ID do Discord é
        # único, estável e não muda com o usuário renomeando a conta.
        nome_canal = f"ticket-{NOMES[valor]}-{membro.id}"

        # Verifica se já tem tíquete aberto dessa categoria
        existente = discord.utils.get(guild.text_channels, name=nome_canal)
        if existente:
            await interaction.response.send_message(
                f"⚠️ Você já tem um tíquete aberto: {existente.mention}",
                ephemeral=True
            )
            return

        # ── Limite de tickets simultâneos (todas as categorias) ──────────
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

        # Marca a tentativa já aqui (antes de criar o canal) para fechar a
        # janela de corrida: dois cliques rápidos em sequência não devem
        # conseguir passar pelo cooldown os dois.
        _ultima_criacao[membro.id] = agora

        # Permissões do canal
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro:             discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        if valor == "dev":
            # Categoria restrita: só quem abriu, o cargo de Desenvolvimento e
            # o cargo da equipe enxergam esse tíquete. Administradores não
            # entram automaticamente aqui (só via cargo da equipe, se tiverem).
            cargo_dev = guild.get_role(CARGO_DESENVOLVIMENTO_ID)
            if cargo_dev is not None:
                overwrites[cargo_dev] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            else:
                print(f"[TICKET] ⚠️ Cargo de Desenvolvimento ({CARGO_DESENVOLVIMENTO_ID}) não encontrado no servidor.")

            cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
            if cargo_equipe is not None:
                overwrites[cargo_equipe] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        else:
            # Administradores também veem
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            cargo_equipe = guild.get_role(CARGO_EQUIPE_ID)
            if cargo_equipe is not None:
                overwrites[cargo_equipe] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            else:
                print(f"[TICKET] ⚠️ Cargo da equipe ({CARGO_EQUIPE_ID}) não encontrado no servidor.")

        # Cria o canal
        canal = await guild.create_text_channel(
            name=nome_canal,
            overwrites=overwrites,
            reason=f"Tíquete aberto por {membro} — {valor}"
        )

        # Registra o tíquete como "aberto" pra rastrear o tempo até a
        # primeira resposta da equipe (usado no card de tempo médio).
        registro_abertos = _ler_abertos()
        registro_abertos[str(canal.id)] = {"criado_em": time.time(), "respondido": False}
        _salvar_abertos(registro_abertos)

        # Embed de abertura dentro do tíquete
        embed = discord.Embed(
            title=f"Tíquete — {self.options[[o.value for o in self.options].index(valor)].label}",
            description=(
                f"Olá, {membro.mention}! 👋\n\n"
                f"A equipe irá te atender em breve.\n"
                f"Descreva seu problema ou dúvida abaixo."
            ),
            color=CORES[valor]
        )
        embed.set_footer(text="Pra fechar este tíquete, clique no botão abaixo.")
        embed.set_thumbnail(url=membro.display_avatar.url)

        # ── Card com o tempo médio de resposta da equipe ─────────────────
        tempos = _ler_tempos()
        total_t = tempos.get("total", 0)
        media_t = (tempos.get("soma_segundos", 0) / total_t) if total_t > 0 else None
        arquivo_imagem = gerar_imagem_tempo_resposta(media_t, total_t)
        if arquivo_imagem:
            embed.set_image(url="attachment://tempo_resposta.png")

        # Botão de fechar
        view = FecharTicketView()
        if arquivo_imagem:
            await canal.send(content=membro.mention, embed=embed, view=view, file=arquivo_imagem)
        else:
            await canal.send(content=membro.mention, embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Tíquete aberto! Acesse: {canal.mention}",
            ephemeral=True
        )
        print(f"[TICKET] ✅ Canal {nome_canal} criado para {membro}.")


# ── Botão de fechar tíquete ────────────────────────────────────────────────────
class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fechar Tíquete", style=discord.ButtonStyle.danger, custom_id="fechar_ticket")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Normalmente só administradores fecham. Exceção: nos tíquetes de
        # Desenvolvimento, administradores não têm acesso automático ao
        # canal, então o próprio cargo de Desenvolvimento também pode fechar.
        pode_fechar = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_fechar and interaction.channel.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_fechar = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)

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


# ── Botão de reabrir tíquete (aparece na mensagem de fechamento) ────────────
class ReabrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔓 Reabrir Tíquete", style=discord.ButtonStyle.success, custom_id="reabrir_ticket")
    async def reabrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel

        # Mesma regra de permissão do botão de fechar: administradores, staff
        # (cargo de equipe) e, nos tíquetes de Desenvolvimento, o próprio
        # cargo de Desenvolvimento também pode reabrir.
        pode_reabrir = (
            interaction.user.guild_permissions.administrator
            or mu.eh_super_admin(interaction.user.id)
            or any(role.id == CARGO_EQUIPE_ID for role in interaction.user.roles)
        )
        if not pode_reabrir and canal.name.startswith(f"ticket-{NOMES['dev']}-"):
            pode_reabrir = any(role.id == CARGO_DESENVOLVIMENTO_ID for role in interaction.user.roles)

        if not pode_reabrir:
            await interaction.response.send_message(
                "❌ Você não tem permissão para reabrir este tíquete.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.reabrir_ticket(interaction)


# ── Escolha: fechar (mantém o canal) ou deletar de vez ──────────────────────
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


# ── View do setup (Select Menu) ────────────────────────────────────────────────
class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ── Cog principal ──────────────────────────────────────────────────────────────
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Extrai o ID de quem abriu o tíquete a partir do nome do canal ──────
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

    # ── Rastreia o tempo até a primeira resposta da equipe num tíquete ─────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        canal = message.channel
        if not isinstance(canal, discord.TextChannel) or not canal.name.startswith("ticket-"):
            return

        dono_id = self._extrair_dono_id(canal.name)
        if dono_id is None or message.author.id == dono_id:
            return  # só conta como "resposta" quem não é o dono do tíquete

        abertos = _ler_abertos()
        info = abertos.get(str(canal.id))
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

    # ── Clique nas estrelas de avaliação (custom_id: ticket_avaliacao_N_donoId) ──
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

    # ── Registra uma nota e atualiza a embed de média no canal do setup ────
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

    # ── Fecha (mantém) ou deleta o tíquete: transcript + avaliação + DM ────
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

        # ── Transcrição em HTML ─────────────────────────────────────────
        arquivo_transcript = None
        try:
            arquivo_transcript = await gerar_transcript_html(canal)
        except Exception as e:
            print(f"[TICKET] ⚠️ Erro ao gerar transcript de #{canal.name}: {e}")

        # ── Pede pro dono avaliar o atendimento, direto no canal ────────
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

        # ── Manda a transcrição na DM de quem abriu o tíquete ────────────
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
            try:
                await canal.send("🗑️ Este tíquete será **deletado** em instantes. A transcrição foi enviada na sua DM.")
            except discord.HTTPException:
                pass
            try:
                await interaction.followup.send("🗑️ Tíquete será deletado em alguns segundos...", ephemeral=True)
            except discord.HTTPException:
                pass
            await asyncio.sleep(8)
            await canal.delete(reason=f"Tíquete deletado por {interaction.user}")
            print(f"[TICKET] 🗑️ Canal {canal.name} deletado por {interaction.user}.")
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

    # ── Reabre um tíquete previamente fechado (canal mantido) ───────────────
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

        # Devolve a permissão de escrever pro dono do tíquete
        if isinstance(dono, discord.Member):
            try:
                await canal.set_permissions(dono, view_channel=True, send_messages=True)
            except discord.Forbidden:
                pass

        # Volta a contar o tempo de resposta como se o tíquete tivesse
        # acabado de ser aberto de novo (senão a métrica de tempo médio de
        # resposta ficaria com um tíquete "fechado" preso pra sempre).
        registro_abertos = _ler_abertos()
        registro_abertos[str(canal.id)] = {"criado_em": time.time(), "respondido": False}
        _salvar_abertos(registro_abertos)

        # Remove o botão "Reabrir" da mensagem antiga de fechamento
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

        # ── Atualiza o painel já existente em vez de mandar um novo ──────
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

    @setup.error
    async def setup_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa ser **Administrador** para usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
