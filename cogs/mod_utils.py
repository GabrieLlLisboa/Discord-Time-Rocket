from __future__ import annotations

import discord
import json
import os
import re
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
#  Módulo: Núcleo do Sistema de Moderação
#  Arquivo: cogs/mod_utils.py
#
#  Tudo que os cogs de moderação (moderation.py, automod.py, antiraid.py,
#  mod_config.py, mod_setup.py) usam em comum:
#   • "Banco de dados" em JSON (config por servidor, punições, automod, anti-raid)
#   • Checagem de hierarquia de cargos
#   • Embeds padronizados
#   • Envio pro canal de log de moderação configurável
#   • View de confirmação genérica pra ações perigosas
#   • Parser de duração ("10m", "1h30m", "7d" etc.)
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ARQUIVOS = {
    "mod_config":     f"{DATA_DIR}/mod_config.json",      # {guild_id: {...config...}}
    "punicoes":       f"{DATA_DIR}/mod_punicoes.json",    # {guild_id: [ {...}, ... ]}
    "automod":        f"{DATA_DIR}/mod_automod.json",     # {guild_id: {...config...}}
    "antiraid":       f"{DATA_DIR}/mod_antiraid.json",    # {guild_id: {...config...}}
    "antinuke":       f"{DATA_DIR}/mod_antinuke.json",    # {guild_id: {...config...}}
}

# ── Cores padrão (Discord brand colors, mesmo padrão usado em cogs/logs.py) ──
COR_SUCESSO   = 0x57F287  # verde
COR_ERRO      = 0xED4245  # vermelho
COR_ALERTA    = 0xFEE75C  # amarelo
COR_INFO      = 0x5865F2  # azul blurple
COR_MODERACAO = 0xED4245  # vermelho
COR_NEUTRO    = 0x2B2D31  # cinza escuro (dark theme)


# ── Leitura / escrita genérica ───────────────────────────────────────────────
def _ler_raw(chave: str) -> dict:
    path = ARQUIVOS[chave]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _salvar_raw(chave: str, dados: dict):
    path = ARQUIVOS[chave]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


for _chave in ARQUIVOS:
    if not os.path.exists(ARQUIVOS[_chave]):
        _salvar_raw(_chave, {})


# ── Configuração por servidor ────────────────────────────────────────────────
CONFIG_PADRAO = {
    "canal_logs_mod": None,       # canal onde vão os logs de moderação
    "canal_logs_automod": None,   # canal onde vão os logs do automod
    "canal_logs_antiraid": None,  # canal onde vão os logs do anti-raid
    "cargo_mute": None,           # cargo usado como "silenciado" (softban/backup de timeout)
    "cargos_staff": [],           # cargos que têm imunidade a automod/anti-raid e podem moderar
    "cargos_imunes_automod": [],  # cargos que não sofrem ação do automod
    "dm_ao_punir": True,          # manda DM pro usuário avisando da punição
    "exigir_confirmacao": True,   # exige confirmação em ban/kick/clear/softban/tempban
    "mensagem_boas_vindas_regras": None,
}


def get_config(guild_id: int) -> dict:
    dados = _ler_raw("mod_config")
    cfg = dict(CONFIG_PADRAO)
    cfg.update(dados.get(str(guild_id), {}))
    return cfg


def salvar_config(guild_id: int, cfg: dict):
    dados = _ler_raw("mod_config")
    dados[str(guild_id)] = cfg
    _salvar_raw("mod_config", dados)


def atualizar_config(guild_id: int, **kwargs) -> dict:
    cfg = get_config(guild_id)
    cfg.update(kwargs)
    salvar_config(guild_id, cfg)
    return cfg


# ── AutoMod: configuração por servidor ───────────────────────────────────────
AUTOMOD_PADRAO = {
    "ativo": True,
    "anti_spam": True,
    "anti_spam_limite": 5,          # nº de mensagens
    "anti_spam_intervalo": 5,       # em segundos
    "anti_flood": True,
    "anti_flood_limite": 3,         # mensagens idênticas seguidas
    "anti_links": False,            # bloqueia qualquer link
    "anti_convites": True,          # bloqueia convites de outros servidores
    "links_whitelist": [],          # domínios liberados quando anti_links = True
    "palavras_proibidas": [],
    "anti_caps": True,
    "anti_caps_percentual": 70,     # % de maiúsculas pra acionar (msg com 8+ caracteres)
    "anti_mencoes": True,
    "anti_mencoes_limite": 5,       # nº de menções numa única mensagem
    "anti_emojis": True,
    "anti_emojis_limite": 10,       # nº de emojis numa única mensagem
    "anti_phishing": True,
    "acao_padrao": "apagar_avisar",  # apagar_avisar | timeout | kick
    "timeout_segundos": 600,
    "log_apenas": False,
}


def get_automod(guild_id: int) -> dict:
    dados = _ler_raw("automod")
    cfg = dict(AUTOMOD_PADRAO)
    cfg.update(dados.get(str(guild_id), {}))
    return cfg


def salvar_automod(guild_id: int, cfg: dict):
    dados = _ler_raw("automod")
    dados[str(guild_id)] = cfg
    _salvar_raw("automod", dados)


def atualizar_automod(guild_id: int, **kwargs) -> dict:
    cfg = get_automod(guild_id)
    cfg.update(kwargs)
    salvar_automod(guild_id, cfg)
    return cfg


# ── Anti-Raid: configuração por servidor ─────────────────────────────────────
ANTIRAID_PADRAO = {
    "ativo": True,
    "janela_segundos": 10,        # janela de tempo pra contar entradas
    "limite_entradas": 8,         # nº de entradas na janela pra considerar raid
    "conta_nova_dias": 7,         # conta com menos que isso é "suspeita"
    "acao": "kick",               # kick | ban | quarentena
    "cargo_quarentena": None,
    "modo_emergencia": False,     # trava entrada de novos membros (verification / lockdown manual)
    "bloquear_conta_sem_avatar": False,
}


def get_antiraid(guild_id: int) -> dict:
    dados = _ler_raw("antiraid")
    cfg = dict(ANTIRAID_PADRAO)
    cfg.update(dados.get(str(guild_id), {}))
    return cfg


def salvar_antiraid(guild_id: int, cfg: dict):
    dados = _ler_raw("antiraid")
    dados[str(guild_id)] = cfg
    _salvar_raw("antiraid", dados)


def atualizar_antiraid(guild_id: int, **kwargs) -> dict:
    cfg = get_antiraid(guild_id)
    cfg.update(kwargs)
    salvar_antiraid(guild_id, cfg)
    return cfg


# ── Anti-Nuke: configuração por servidor ─────────────────────────────────────
# Protege o servidor contra staff comprometido/mal-intencionado que sai
# deletando canais, cargos ou banindo membros em massa. Quando detecta,
# remove imediatamente os cargos perigosos de quem estiver fazendo isso
# (kick/ban do bot não bastam se a conta ainda tem cargo de admin).
ANTINUKE_PADRAO = {
    "ativo": True,
    "janela_segundos": 20,          # janela de tempo pra contar ações
    "limite_canais": 3,             # nº de canais criados/deletados na janela pra acionar
    "limite_cargos": 3,             # nº de cargos criados/deletados na janela pra acionar
    "limite_banimentos": 4,         # nº de banimentos na janela pra acionar
    "limite_expulsoes": 5,          # nº de expulsões (kicks) na janela pra acionar
    "acao": "remover_cargos",       # remover_cargos | quarentena | ban
    "cargo_quarentena": None,
    "whitelist_ids": [],            # IDs de usuários/bots confiáveis, imunes ao anti-nuke
    "punir_bots_nao_whitelistados": True,
}


def get_antinuke(guild_id: int) -> dict:
    dados = _ler_raw("antinuke")
    cfg = dict(ANTINUKE_PADRAO)
    cfg.update(dados.get(str(guild_id), {}))
    return cfg


def salvar_antinuke(guild_id: int, cfg: dict):
    dados = _ler_raw("antinuke")
    dados[str(guild_id)] = cfg
    _salvar_raw("antinuke", dados)


def atualizar_antinuke(guild_id: int, **kwargs) -> dict:
    cfg = get_antinuke(guild_id)
    cfg.update(kwargs)
    salvar_antinuke(guild_id, cfg)
    return cfg


# ── Punições: histórico permanente por servidor ──────────────────────────────
def _proximo_id(registros: list) -> int:
    return (max((r["id"] for r in registros), default=0)) + 1


def registrar_punicao(guild_id: int, user_id: int, moderador_id: int, tipo: str,
                       motivo: str = "Não informado", duracao_segundos: int | None = None) -> dict:
    dados = _ler_raw("punicoes")
    chave = str(guild_id)
    registros = dados.get(chave, [])

    agora = datetime.now(timezone.utc)
    expira_em = None
    if duracao_segundos:
        expira_em = (agora + timedelta(seconds=duracao_segundos)).isoformat()

    registro = {
        "id": _proximo_id(registros),
        "user_id": user_id,
        "moderador_id": moderador_id,
        "tipo": tipo,          # warn | timeout | kick | ban | tempban | softban | unban
        "motivo": motivo,
        "criado_em": agora.isoformat(),
        "expira_em": expira_em,
        "ativo": True,
    }
    registros.append(registro)
    dados[chave] = registros
    _salvar_raw("punicoes", dados)
    return registro


def historico_usuario(guild_id: int, user_id: int) -> list:
    dados = _ler_raw("punicoes")
    registros = dados.get(str(guild_id), [])
    return [r for r in registros if r["user_id"] == user_id]


def avisos_usuario(guild_id: int, user_id: int, apenas_ativos: bool = True) -> list:
    regs = [r for r in historico_usuario(guild_id, user_id) if r["tipo"] == "warn"]
    if apenas_ativos:
        regs = [r for r in regs if r.get("ativo", True)]
    return regs


def remover_punicao(guild_id: int, punicao_id: int) -> bool:
    dados = _ler_raw("punicoes")
    chave = str(guild_id)
    registros = dados.get(chave, [])
    for r in registros:
        if r["id"] == punicao_id:
            r["ativo"] = False
            _salvar_raw("punicoes", dados)
            return True
    return False


def punicoes_ativas_temporarias(guild_id: int) -> list:
    """Retorna tempbans/timeouts com expira_em no futuro, usados pelo loop de checagem."""
    dados = _ler_raw("punicoes")
    registros = dados.get(str(guild_id), [])
    return [r for r in registros if r.get("ativo") and r.get("expira_em")]


# ── Hierarquia de permissões ─────────────────────────────────────────────────
def eh_staff(member: discord.Member, guild_id: int) -> bool:
    """Considera staff quem tem permissão de moderar OU tem um dos cargos configurados."""
    if member.guild_permissions.moderate_members or member.guild_permissions.administrator:
        return True
    cfg = get_config(guild_id)
    cargos_staff = set(cfg.get("cargos_staff", []))
    return any(r.id in cargos_staff for r in member.roles)


def pode_moderar(moderador: discord.Member, alvo: discord.Member) -> tuple[bool, str]:
    """
    Verifica se `moderador` pode aplicar uma ação de moderação sobre `alvo`,
    respeitando a hierarquia de cargos do Discord.
    """
    guild = moderador.guild
    if alvo.id == moderador.id:
        return False, "❌ Você não pode se moderar."
    if alvo.id == guild.owner_id:
        return False, "❌ Não é possível moderar o dono do servidor."
    if alvo.bot and alvo.id == guild.me.id:
        return False, "❌ Não posso me moderar."
    if moderador.id != guild.owner_id and alvo.top_role >= moderador.top_role:
        return False, "❌ Você não tem cargo suficiente pra moderar esse usuário (hierarquia de cargos)."
    if alvo.top_role >= guild.me.top_role and alvo.id != guild.me.id:
        return False, "❌ Meu cargo está abaixo (ou igual) ao do usuário — preciso estar mais alto na hierarquia."
    return True, ""


# ── Embeds padronizados ──────────────────────────────────────────────────────
def embed_base(titulo: str, descricao: str = "", cor: int = COR_INFO) -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao, color=cor, timestamp=datetime.now(timezone.utc))
    return e


def embed_sucesso(descricao: str, titulo: str = "✅ Sucesso") -> discord.Embed:
    return embed_base(titulo, descricao, COR_SUCESSO)


def embed_erro(descricao: str, titulo: str = "❌ Erro") -> discord.Embed:
    return embed_base(titulo, descricao, COR_ERRO)


EMOJIS_TIPO = {
    "warn": "⚠️", "timeout": "🔇", "kick": "👢", "ban": "🔨",
    "tempban": "⏳🔨", "unban": "♻️", "softban": "🧹🔨",
    "clear": "🧽", "slowmode": "🐌", "nick": "✏️",
    "lock": "🔒", "unlock": "🔓",
}


def embed_punicao(tipo: str, alvo: discord.abc.User, moderador: discord.abc.User,
                   motivo: str, duracao_texto: str | None = None, punicao_id: int | None = None) -> discord.Embed:
    emoji = EMOJIS_TIPO.get(tipo, "🛠️")
    e = discord.Embed(
        title=f"{emoji} {tipo.capitalize()} aplicado",
        color=COR_MODERACAO,
        timestamp=datetime.now(timezone.utc),
    )
    e.add_field(name="Usuário", value=f"{alvo.mention} (`{alvo.id}`)", inline=False)
    e.add_field(name="Responsável", value=f"{moderador.mention} (`{moderador.id}`)", inline=False)
    e.add_field(name="Motivo", value=motivo or "Não informado", inline=False)
    if duracao_texto:
        e.add_field(name="Duração", value=duracao_texto, inline=False)
    if punicao_id:
        e.set_footer(text=f"Caso #{punicao_id}")
    if hasattr(alvo, "display_avatar"):
        e.set_thumbnail(url=alvo.display_avatar.url)
    return e


async def enviar_log_moderacao(bot: discord.Client, guild: discord.Guild, embed: discord.Embed):
    cfg = get_config(guild.id)
    canal_id = cfg.get("canal_logs_mod")
    if not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if canal is None:
        try:
            canal = await guild.fetch_channel(canal_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        await canal.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def enviar_log_automod(bot: discord.Client, guild: discord.Guild, embed: discord.Embed):
    cfg = get_config(guild.id)
    canal_id = cfg.get("canal_logs_automod") or cfg.get("canal_logs_mod")
    if not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if canal is None:
        try:
            canal = await guild.fetch_channel(canal_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        await canal.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def enviar_log_antiraid(bot: discord.Client, guild: discord.Guild, embed: discord.Embed):
    cfg = get_config(guild.id)
    canal_id = cfg.get("canal_logs_antiraid") or cfg.get("canal_logs_mod")
    if not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if canal is None:
        try:
            canal = await guild.fetch_channel(canal_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        await canal.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def enviar_log_antinuke(bot: discord.Client, guild: discord.Guild, embed: discord.Embed):
    cfg = get_config(guild.id)
    canal_id = cfg.get("canal_logs_antiraid") or cfg.get("canal_logs_mod")
    if not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if canal is None:
        try:
            canal = await guild.fetch_channel(canal_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        await canal.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def notificar_usuario(usuario: discord.abc.User, embed: discord.Embed):
    """Tenta mandar DM pro usuário. Falha silenciosamente se ele tiver DMs fechadas."""
    try:
        await usuario.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


# ── Parser de duração: "10m", "1h30m", "7d", "45s" ───────────────────────────
UNIDADES = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
REGEX_DURACAO = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)


def parsear_duracao(texto: str) -> int | None:
    """Converte algo como '1h30m' em segundos. Retorna None se inválido."""
    if not texto:
        return None
    texto = texto.strip().lower()
    total = 0
    encontrou = False
    for valor, unidade in REGEX_DURACAO.findall(texto):
        total += int(valor) * UNIDADES[unidade]
        encontrou = True
    return total if encontrou and total > 0 else None


def formatar_duracao(segundos: int) -> str:
    if segundos <= 0:
        return "0s"
    partes = []
    for nome, tamanho in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if segundos >= tamanho:
            qtd, segundos = divmod(segundos, tamanho)
            partes.append(f"{qtd}{nome}")
    return " ".join(partes) if partes else "0s"


# ── View de confirmação genérica pra ações perigosas ─────────────────────────
class ConfirmarView(discord.ui.View):
    """
    View reutilizável de confirmação (Sim/Não). Só quem invocou o comando
    pode responder. Uso:

        view = ConfirmarView(autor_id=interaction.user.id)
        await interaction.response.send_message(embed=..., view=view)
        await view.esperar()
        if view.valor:
            ...executa a ação...
    """
    def __init__(self, autor_id: int, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.autor_id = autor_id
        self.valor: bool | None = None
        self.interacao_resposta: discord.Interaction | None = None
        self._evento = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Só quem executou o comando pode confirmar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.valor = True
        self.interacao_resposta = interaction
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.valor = False
        self.interacao_resposta = interaction
        self.stop()

    async def on_timeout(self):
        self.valor = False


async def confirmar_acao(interaction: discord.Interaction, titulo: str, descricao: str,
                          exigir: bool = True) -> tuple[bool, discord.Interaction]:
    """
    Mostra um prompt de confirmação (se `exigir` for True) e retorna
    (confirmado, interacao_a_usar_pra_responder_depois).
    Se `exigir` for False, confirma automaticamente sem perguntar.
    """
    if not exigir:
        return True, interaction

    view = ConfirmarView(autor_id=interaction.user.id)
    embed = embed_base(f"⚠️ {titulo}", descricao, COR_ALERTA)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    await view.wait()

    if view.valor is None or view.valor is False:
        cancel_embed = embed_erro("Ação cancelada." if view.valor is False else "Tempo esgotado, ação cancelada.")
        try:
            await interaction.edit_original_response(embed=cancel_embed, view=None)
        except discord.HTTPException:
            pass
        return False, interaction

    return True, view.interacao_resposta
