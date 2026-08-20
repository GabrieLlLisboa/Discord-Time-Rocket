from __future__ import annotations

import discord
import json
import os
import re
from datetime import datetime, timezone, timedelta


DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ARQUIVOS = {
    "mod_config":     f"{DATA_DIR}/mod_config.json",
    "punicoes":       f"{DATA_DIR}/mod_punicoes.json",
    "automod":        f"{DATA_DIR}/mod_automod.json",
    "antiraid":       f"{DATA_DIR}/mod_antiraid.json",
    "antinuke":       f"{DATA_DIR}/mod_antinuke.json",
}


COR_SUCESSO   = 0x57F287
COR_ERRO      = 0xED4245
COR_ALERTA    = 0xFEE75C
COR_INFO      = 0x5865F2
COR_MODERACAO = 0xED4245
COR_NEUTRO    = 0x2B2D31


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


CONFIG_PADRAO = {
    "canal_logs_mod": None,
    "canal_logs_automod": None,
    "canal_logs_antiraid": None,
    "cargo_mute": None,
    "cargos_staff": [],
    "cargos_imunes_automod": [],
    "dm_ao_punir": True,
    "exigir_confirmacao": True,
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


AUTOMOD_PADRAO = {
    "ativo": True,
    "anti_spam": True,
    "anti_spam_limite": 5,
    "anti_spam_intervalo": 5,
    "anti_flood": True,
    "anti_flood_limite": 3,
    "anti_links": False,
    "anti_convites": True,
    "links_whitelist": [],
    "palavras_proibidas": [],
    "anti_caps": True,
    "anti_caps_percentual": 70,
    "anti_mencoes": True,
    "anti_mencoes_limite": 8,
    "anti_emojis": True,
    "anti_emojis_limite": 10,
    "anti_phishing": True,
    "acao_padrao": "apagar_avisar",
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


ANTIRAID_PADRAO = {
    "ativo": True,
    "janela_segundos": 10,
    "limite_entradas": 8,
    "conta_nova_dias": 7,
    "acao": "kick",
    "cargo_quarentena": None,
    "modo_emergencia": False,
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


ANTINUKE_PADRAO = {
    "ativo": True,
    "janela_segundos": 20,
    "limite_canais": 3,
    "limite_cargos": 3,
    "limite_banimentos": 4,
    "limite_expulsoes": 5,
    "acao": "remover_cargos",
    "cargo_quarentena": None,
    "whitelist_ids": [],
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
        "tipo": tipo,
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


SUPER_ADMIN_IDS = {1487452210605588592}

# cargo(s) que funcionam como "dono" — quem tiver um desses cargos passa a
# ter acesso liberado nos comandos igual quem tá em SUPER_ADMIN_IDS, sem
# precisar cadastrar o ID da pessoa na mão
SUPER_ADMIN_ROLE_IDS = {1523835085475020932}


def eh_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS


def eh_super_admin_membro(membro) -> bool:
    """Igual eh_super_admin, mas também libera quem tem um dos cargos
    listados em SUPER_ADMIN_ROLE_IDS (não precisa nem ser o dono de fato,
    só ter o cargo)."""
    if eh_super_admin(getattr(membro, "id", None)):
        return True
    cargos = getattr(membro, "roles", None)
    if not cargos:
        return False
    return any(cargo.id in SUPER_ADMIN_ROLE_IDS for cargo in cargos)


def eh_staff(member: discord.Member, guild_id: int) -> bool:
    """Considera staff quem tem permissão de moderar OU tem um dos cargos configurados."""
    if eh_super_admin(member.id):
        return True
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


# IDs dos canais de voz "lobby" pra onde o pessoal é realocado quando um
# amistoso termina e a call dele vai ser apagada.
CANAIS_VOZ_POS_AMISTOSO = [1514777010293964830, 1532926276464279563]


async def mover_membros_pos_amistoso(bot: discord.Client, canal_voz: discord.VoiceChannel):
    """Move todo mundo que ainda tá na call do amistoso pra um canal de voz
    'lobby' antes da call do amistoso ser apagada. Chame isso ANTES de
    deletar o canal de voz do amistoso, senão os membros só são
    desconectados (não são transferidos)."""
    if canal_voz is None:
        return

    membros = list(canal_voz.members)
    if not membros:
        return

    guild = canal_voz.guild
    destinos = [guild.get_channel(cid) for cid in CANAIS_VOZ_POS_AMISTOSO]
    destinos = [c for c in destinos if isinstance(c, discord.VoiceChannel)]
    if not destinos:
        print("[AMISTOSO] ⚠️ Nenhum dos canais de voz de destino (lobby) foi encontrado.")
        return

    destino = next((c for c in destinos if len(c.members) == 0), destinos[0])

    for membro in membros:
        try:
            await membro.move_to(destino, reason="Fim do amistoso — realocado da call do amistoso.")
        except discord.Forbidden:
            print(f"[AMISTOSO] ⚠️ Sem permissão pra mover {membro} pra {destino.name}.")
        except discord.HTTPException as e:
            print(f"[AMISTOSO] ⚠️ Erro ao mover {membro} pra {destino.name}: {e}")


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
