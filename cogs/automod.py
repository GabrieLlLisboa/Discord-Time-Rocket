from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

from cogs import mod_utils as mu
from cogs.json_store import ler_json

# Mesmo arquivo usado por cogs/players.py pra guardar em quais canais o
# painel !setup-rank foi enviado.
_CANAIS_PAINEL_RANK_PATH = "data/canais_painel_rank.json"


def _canais_ignorados_pelo_automod() -> set[int]:
    return set(ler_json(_CANAIS_PAINEL_RANK_PATH, []))


# ─────────────────────────────────────────────────────────────────────────────
#  Cog: AutoMod
#  Arquivo: cogs/automod.py
#
#  Escaneia toda mensagem em busca de:
#   spam, flood (mensagens repetidas), links, convites de outros servidores,
#   palavras proibidas, CAPS excessivo, menções em massa, excesso de emojis
#   e padrões comuns de golpe/phishing.
#
#  Comandos /automod ... pra ligar/desligar filtros e configurar limites.
# ─────────────────────────────────────────────────────────────────────────────

REGEX_LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
REGEX_CONVITE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
REGEX_EMOJI_CUSTOM = re.compile(r"<a?:\w+:\d+>")
REGEX_EMOJI_UNICODE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

# Palavras/padrões comuns em golpes de phishing no Discord (nitro grátis, steam, etc.)
PADROES_PHISHING = [
    r"discord\s*nitro\s*(grátis|gratis|free)",
    r"steam\s*community\s*[a-z0-9.-]*\s*gift",
    r"free\s*nitro",
    r"\bdiscordgift\b",
    r"\bdiscordapp\.gift\b",
    r"\bsteamcommunlty\b",
    r"\bdiscordnitro\b",
]
REGEX_PHISHING = re.compile("|".join(PADROES_PHISHING), re.IGNORECASE)


class Automod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # históricos em memória (não precisam persistir): {(guild_id, user_id): deque[(timestamp, conteudo)]}
        self.historico_msgs: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=15))

    # ── Helpers ───────────────────────────────────────────────────────────
    def _imune(self, membro: discord.Member, cfg_mod: dict) -> bool:
        if membro.bot:
            return True
        if membro.guild_permissions.administrator or membro.guild_permissions.manage_guild:
            return True
        cargos_imunes = set(cfg_mod.get("cargos_imunes_automod", []) + cfg_mod.get("cargos_staff", []))
        return any(r.id in cargos_imunes for r in membro.roles)

    async def _acao(self, message: discord.Message, motivo: str, gatilho: str, cfg_auto: dict):
        """Executa a ação configurada (apagar+avisar, timeout ou kick) e loga."""
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        if not cfg_auto.get("log_apenas"):
            try:
                await message.channel.send(
                    f"⚠️ {message.author.mention}, sua mensagem foi removida pelo AutoMod: **{motivo}**.",
                    delete_after=6,
                )
            except discord.HTTPException:
                pass

        acao = cfg_auto.get("acao_padrao", "apagar_avisar")
        if acao == "timeout" and isinstance(message.author, discord.Member):
            try:
                segundos = int(cfg_auto.get("timeout_segundos", 600))
                await message.author.timeout(discord.utils.utcnow() + timedelta(seconds=segundos), reason=f"AutoMod: {motivo}")
                mu.registrar_punicao(message.guild.id, message.author.id, self.bot.user.id, "timeout", f"[AutoMod] {motivo}", segundos)
            except (discord.Forbidden, discord.HTTPException):
                pass
        elif acao == "kick" and isinstance(message.author, discord.Member):
            try:
                await message.author.kick(reason=f"AutoMod: {motivo}")
                mu.registrar_punicao(message.guild.id, message.author.id, self.bot.user.id, "kick", f"[AutoMod] {motivo}")
            except (discord.Forbidden, discord.HTTPException):
                pass

        embed = mu.embed_base(
            "🛡️ AutoMod: mensagem removida",
            f"**Usuário:** {message.author.mention} (`{message.author.id}`)\n"
            f"**Canal:** {message.channel.mention}\n"
            f"**Motivo:** {motivo}\n"
            f"**Gatilho:** {gatilho[:200]}",
            mu.COR_ALERTA,
        )
        await mu.enviar_log_automod(self.bot, message.guild, embed)

    # ── Listener principal ───────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        # Canal do painel !setup-rank (cogs/players.py): lá as mensagens já
        # são controladas por outro fluxo (comprovação de rank) — o AutoMod
        # não deve mexer nelas, senão apaga o print/link antes do bot
        # conseguir coletar e mandar a pendência pra staff.
        if message.channel.id in _canais_ignorados_pelo_automod():
            return

        cfg_mod = mu.get_config(message.guild.id)
        cfg = mu.get_automod(message.guild.id)
        if not cfg.get("ativo", True):
            return
        if self._imune(message.author, cfg_mod):
            return

        conteudo = message.content or ""
        chave = (message.guild.id, message.author.id)
        agora = time.time()

        # ── Anti-Phishing (prioridade máxima) ────────────────────────────
        if cfg.get("anti_phishing") and REGEX_PHISHING.search(conteudo):
            await self._acao(message, "Link/mensagem de phishing detectado", conteudo, cfg)
            return

        # ── Anti-convites ─────────────────────────────────────────────────
        if cfg.get("anti_convites") and REGEX_CONVITE.search(conteudo):
            await self._acao(message, "Convite de outro servidor não permitido", conteudo, cfg)
            return

        # ── Anti-links ────────────────────────────────────────────────────
        if cfg.get("anti_links"):
            achados = REGEX_LINK.findall(conteudo)
            if achados:
                whitelist = cfg.get("links_whitelist", [])
                permitido = any(dom in conteudo for dom in whitelist)
                if not permitido:
                    await self._acao(message, "Envio de link não permitido", conteudo, cfg)
                    return

        # ── Palavras proibidas ───────────────────────────────────────────
        proibidas = cfg.get("palavras_proibidas", [])
        if proibidas:
            texto_lower = conteudo.lower()
            for palavra in proibidas:
                if re.search(rf"\b{re.escape(palavra.lower())}\b", texto_lower):
                    await self._acao(message, "Palavra proibida detectada", palavra, cfg)
                    return

        # ── CAPS excessivo ────────────────────────────────────────────────
        if cfg.get("anti_caps"):
            letras = [c for c in conteudo if c.isalpha()]
            if len(letras) >= 8:
                maiusculas = sum(1 for c in letras if c.isupper())
                percentual = (maiusculas / len(letras)) * 100
                if percentual >= cfg.get("anti_caps_percentual", 70):
                    await self._acao(message, "Excesso de letras maiúsculas (CAPS)", conteudo, cfg)
                    return

        # ── Menções em massa ──────────────────────────────────────────────
        if cfg.get("anti_mencoes"):
            total_mencoes = len(message.mentions) + len(message.role_mentions)
            if total_mencoes >= cfg.get("anti_mencoes_limite", 5):
                await self._acao(message, "Menções em massa", f"{total_mencoes} menções", cfg)
                return

        # ── Excesso de emojis ─────────────────────────────────────────────
        if cfg.get("anti_emojis"):
            total_emojis = len(REGEX_EMOJI_CUSTOM.findall(conteudo)) + len(REGEX_EMOJI_UNICODE.findall(conteudo))
            if total_emojis >= cfg.get("anti_emojis_limite", 10):
                await self._acao(message, "Excesso de emojis", f"{total_emojis} emojis", cfg)
                return

        # ── Anti-spam / anti-flood (usa o histórico em memória) ──────────
        historico = self.historico_msgs[chave]
        historico.append((agora, conteudo))

        if cfg.get("anti_spam"):
            intervalo = cfg.get("anti_spam_intervalo", 5)
            limite = cfg.get("anti_spam_limite", 5)
            recentes = [t for t, _ in historico if agora - t <= intervalo]
            if len(recentes) >= limite:
                await self._acao(message, "Spam detectado (muitas mensagens em pouco tempo)", conteudo, cfg)
                historico.clear()
                return

        if cfg.get("anti_flood"):
            limite_flood = cfg.get("anti_flood_limite", 3)
            if len(historico) >= limite_flood:
                ultimas = list(historico)[-limite_flood:]
                if len({c for _, c in ultimas}) == 1 and conteudo.strip():
                    await self._acao(message, "Flood detectado (mensagens repetidas)", conteudo, cfg)
                    historico.clear()
                    return

    # ── /automod (grupo de configuração) ─────────────────────────────────
    automod_group = app_commands.Group(name="automod", description="Configurações do sistema de AutoMod.",
                                        default_permissions=discord.Permissions(manage_guild=True))

    @automod_group.command(name="status", description="Mostra a configuração atual do AutoMod.")
    async def automod_status(self, interaction: discord.Interaction):
        cfg = mu.get_automod(interaction.guild_id)
        linhas = [
            f"**Ativo:** {'✅' if cfg['ativo'] else '❌'}",
            f"**Anti-spam:** {'✅' if cfg['anti_spam'] else '❌'} ({cfg['anti_spam_limite']} msgs / {cfg['anti_spam_intervalo']}s)",
            f"**Anti-flood:** {'✅' if cfg['anti_flood'] else '❌'} ({cfg['anti_flood_limite']} repetidas)",
            f"**Anti-links:** {'✅' if cfg['anti_links'] else '❌'}",
            f"**Anti-convites:** {'✅' if cfg['anti_convites'] else '❌'}",
            f"**Anti-CAPS:** {'✅' if cfg['anti_caps'] else '❌'} ({cfg['anti_caps_percentual']}%)",
            f"**Anti-menções em massa:** {'✅' if cfg['anti_mencoes'] else '❌'} (limite {cfg['anti_mencoes_limite']})",
            f"**Anti-emojis em excesso:** {'✅' if cfg['anti_emojis'] else '❌'} (limite {cfg['anti_emojis_limite']})",
            f"**Anti-phishing:** {'✅' if cfg['anti_phishing'] else '❌'}",
            f"**Palavras proibidas cadastradas:** {len(cfg['palavras_proibidas'])}",
            f"**Ação padrão:** `{cfg['acao_padrao']}`",
        ]
        embed = mu.embed_base("🛡️ Configuração do AutoMod", "\n".join(linhas), mu.COR_INFO)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="ativar", description="Liga ou desliga um filtro específico do AutoMod.")
    @app_commands.describe(filtro="Qual filtro alterar", ativo="Ligar (true) ou desligar (false)")
    @app_commands.choices(filtro=[
        app_commands.Choice(name="Sistema completo", value="ativo"),
        app_commands.Choice(name="Anti-spam", value="anti_spam"),
        app_commands.Choice(name="Anti-flood", value="anti_flood"),
        app_commands.Choice(name="Anti-links", value="anti_links"),
        app_commands.Choice(name="Anti-convites", value="anti_convites"),
        app_commands.Choice(name="Anti-CAPS", value="anti_caps"),
        app_commands.Choice(name="Anti-menções em massa", value="anti_mencoes"),
        app_commands.Choice(name="Anti-emojis em excesso", value="anti_emojis"),
        app_commands.Choice(name="Anti-phishing", value="anti_phishing"),
        app_commands.Choice(name="Apenas logar (não punir)", value="log_apenas"),
    ])
    async def automod_ativar(self, interaction: discord.Interaction, filtro: app_commands.Choice[str], ativo: bool):
        mu.atualizar_automod(interaction.guild_id, **{filtro.value: ativo})
        await interaction.response.send_message(embed=mu.embed_sucesso(f"**{filtro.name}** agora está {'✅ ativado' if ativo else '❌ desativado'}."), ephemeral=True)

    @automod_group.command(name="acao", description="Define a ação aplicada quando o AutoMod pega uma violação.")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Apagar e avisar", value="apagar_avisar"),
        app_commands.Choice(name="Apagar e aplicar timeout", value="timeout"),
        app_commands.Choice(name="Apagar e expulsar (kick)", value="kick"),
    ])
    async def automod_acao(self, interaction: discord.Interaction, acao: app_commands.Choice[str]):
        mu.atualizar_automod(interaction.guild_id, acao_padrao=acao.value)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Ação padrão do AutoMod definida como **{acao.name}**."), ephemeral=True)

    @automod_group.command(name="palavra-adicionar", description="Adiciona uma palavra à lista de proibidas.")
    async def automod_palavra_add(self, interaction: discord.Interaction, palavra: str):
        cfg = mu.get_automod(interaction.guild_id)
        lista = cfg.get("palavras_proibidas", [])
        if palavra.lower() in [p.lower() for p in lista]:
            return await interaction.response.send_message(embed=mu.embed_erro("Essa palavra já está na lista."), ephemeral=True)
        lista.append(palavra.lower())
        mu.atualizar_automod(interaction.guild_id, palavras_proibidas=lista)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Palavra adicionada à lista de proibidas. Total: {len(lista)}."), ephemeral=True)

    @automod_group.command(name="palavra-remover", description="Remove uma palavra da lista de proibidas.")
    async def automod_palavra_remover(self, interaction: discord.Interaction, palavra: str):
        cfg = mu.get_automod(interaction.guild_id)
        lista = [p for p in cfg.get("palavras_proibidas", []) if p.lower() != palavra.lower()]
        mu.atualizar_automod(interaction.guild_id, palavras_proibidas=lista)
        await interaction.response.send_message(embed=mu.embed_sucesso("Palavra removida (se existia) da lista."), ephemeral=True)

    @automod_group.command(name="whitelist-link", description="Adiciona um domínio à whitelist de links permitidos.")
    async def automod_whitelist_link(self, interaction: discord.Interaction, dominio: str):
        cfg = mu.get_automod(interaction.guild_id)
        lista = cfg.get("links_whitelist", [])
        if dominio not in lista:
            lista.append(dominio)
        mu.atualizar_automod(interaction.guild_id, links_whitelist=lista)
        await interaction.response.send_message(embed=mu.embed_sucesso(f"Domínio **{dominio}** liberado."), ephemeral=True)

    @automod_group.command(name="limite", description="Ajusta um limite numérico do AutoMod.")
    @app_commands.choices(config=[
        app_commands.Choice(name="Limite de mensagens (anti-spam)", value="anti_spam_limite"),
        app_commands.Choice(name="Intervalo em segundos (anti-spam)", value="anti_spam_intervalo"),
        app_commands.Choice(name="Repetições seguidas (anti-flood)", value="anti_flood_limite"),
        app_commands.Choice(name="Percentual de CAPS", value="anti_caps_percentual"),
        app_commands.Choice(name="Limite de menções", value="anti_mencoes_limite"),
        app_commands.Choice(name="Limite de emojis", value="anti_emojis_limite"),
        app_commands.Choice(name="Duração do timeout (segundos)", value="timeout_segundos"),
    ])
    async def automod_limite(self, interaction: discord.Interaction, config: app_commands.Choice[str], valor: app_commands.Range[int, 1, 100000]):
        mu.atualizar_automod(interaction.guild_id, **{config.value: valor})
        await interaction.response.send_message(embed=mu.embed_sucesso(f"**{config.name}** definido como `{valor}`."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Automod(bot))
