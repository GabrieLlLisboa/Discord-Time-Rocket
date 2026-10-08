from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

from cogs import mod_utils as mu


REGEX_LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
REGEX_CONVITE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
REGEX_EMOJI_CUSTOM = re.compile(r"<a?:\w+:\d+>")
REGEX_EMOJI_UNICODE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)


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

# IDs de usuário que devem ser expulsos automaticamente ao enviar qualquer mensagem
IDS_EXPULSAO_AUTOMATICA = set()

# IDs de canais onde qualquer pessoa que mandar mensagem é expulsa automaticamente do servidor
CANAIS_EXPULSAO_AUTOMATICA = {1539989820137275392}

# Anti-spam / anti-flood: depois de pegar alguém, o bot apaga TUDO que a pessoa mandar
# até ela ficar FLOOD_CASTIGO_SEGUNDOS sem mandar nada (cada mensagem apagada renova
# esse tempo). Sem isso a pessoa voltava a "zerar" a contagem e passavam 2 de cada 3.
FLOOD_CASTIGO_SEGUNDOS = 8

# Mensagens iguais seguidas só contam como flood se forem enviadas dentro dessa janela
# (configurável em /automod limite -> anti_flood_janela). Antes não tinha limite de
# tempo: "ok", "ok", "ok" com uma hora de diferença virava flood.
FLOOD_JANELA_PADRAO = 30


class Automod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # (momento, texto_normalizado, id_canal, id_mensagem) — só ids, não guarda a mensagem inteira
        self.historico_msgs: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=60))
        # (servidor, usuário) -> até quando tudo que a pessoa mandar é apagado (castigo do flood/spam)
        self.castigo_ate: dict[tuple[int, int], float] = {}


    def _imune(self, membro: discord.Member, cfg_mod: dict) -> bool:
        if membro.bot:
            return True
        if mu.eh_super_admin(membro.id):
            return True
        if membro.guild_permissions.administrator or membro.guild_permissions.manage_guild:
            return True
        cargos_imunes = set(cfg_mod.get("cargos_imunes_automod", []) + cfg_mod.get("cargos_staff", []))
        return any(r.id in cargos_imunes for r in membro.roles)

    async def _apagar_ids(self, canal_id: int, ids: list[int]):
        """Apaga várias mensagens de uma vez (uma chamada só, bem mais rápido que uma a uma);
        se o Discord recusar (mensagem velha, já apagada...), tenta uma por uma."""
        canal = self.bot.get_channel(canal_id)
        if canal is None or not ids:
            return
        try:
            if len(ids) >= 2:
                await canal.delete_messages([discord.Object(id=i) for i in ids])
            else:
                await canal.get_partial_message(ids[0]).delete()
            return
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            pass
        for i in ids:
            try:
                await canal.get_partial_message(i).delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
                pass

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


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        if message.author.id in IDS_EXPULSAO_AUTOMATICA:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await message.author.kick(reason="AutoMod: ID na lista de expulsão automática")
                mu.registrar_punicao(
                    message.guild.id,
                    message.author.id,
                    self.bot.user.id,
                    "kick",
                    "[AutoMod] ID na lista de expulsão automática",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        cfg_mod = mu.get_config(message.guild.id)

        if message.channel.id in CANAIS_EXPULSAO_AUTOMATICA and not self._imune(message.author, cfg_mod):
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await message.author.kick(reason="AutoMod: mensagem enviada em canal de expulsão automática")
                mu.registrar_punicao(
                    message.guild.id,
                    message.author.id,
                    self.bot.user.id,
                    "kick",
                    "[AutoMod] Mensagem enviada em canal restrito (expulsão automática)",
                )
                embed = mu.embed_base(
                    "🛡️ AutoMod: expulsão automática por canal",
                    f"**Usuário:** {message.author.mention} (`{message.author.id}`)\n"
                    f"**Canal:** {message.channel.mention}\n"
                    f"**Motivo:** Envio de mensagem em canal proibido para membros comuns.",
                    mu.COR_ALERTA,
                )
                await mu.enviar_log_automod(self.bot, message.guild, embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
            return
        cfg = mu.get_automod(message.guild.id)
        if not cfg.get("ativo", True):
            return
        if self._imune(message.author, cfg_mod):
            return

        conteudo = message.content or ""
        chave = (message.guild.id, message.author.id)
        agora = time.time()

        # Já foi pego por spam/flood agora há pouco? Apaga tudo em silêncio (sem novo aviso
        # nem novo log a cada mensagem) até a pessoa parar.
        castigo_ate = self.castigo_ate.get(chave)
        if castigo_ate is not None:
            if agora < castigo_ate:
                self.castigo_ate[chave] = agora + FLOOD_CASTIGO_SEGUNDOS
                await self._apagar_ids(message.channel.id, [message.id])
                return
            self.castigo_ate.pop(chave, None)


        if cfg.get("anti_phishing") and REGEX_PHISHING.search(conteudo):
            await self._acao(message, "Link/mensagem de phishing detectado", conteudo, cfg)
            return


        if cfg.get("anti_convites") and REGEX_CONVITE.search(conteudo):
            await self._acao(message, "Convite de outro servidor não permitido", conteudo, cfg)
            return


        if cfg.get("anti_links"):
            achados = REGEX_LINK.findall(conteudo)
            if achados:
                whitelist = cfg.get("links_whitelist", [])
                permitido = any(dom in conteudo for dom in whitelist)
                if not permitido:
                    await self._acao(message, "Envio de link não permitido", conteudo, cfg)
                    return


        proibidas = cfg.get("palavras_proibidas", [])
        if proibidas:
            texto_lower = conteudo.lower()
            for palavra in proibidas:
                if re.search(rf"\b{re.escape(palavra.lower())}\b", texto_lower):
                    await self._acao(message, "Palavra proibida detectada", palavra, cfg)
                    return


        if cfg.get("anti_caps"):
            letras = [c for c in conteudo if c.isalpha()]
            if len(letras) >= 8:
                maiusculas = sum(1 for c in letras if c.isupper())
                percentual = (maiusculas / len(letras)) * 100
                if percentual >= cfg.get("anti_caps_percentual", 70):
                    await self._acao(message, "Excesso de letras maiúsculas (CAPS)", conteudo, cfg)
                    return


        if cfg.get("anti_mencoes") and message.mention_everyone:
            await self._acao(message, "Menção a @everyone/@here por quem não é staff", conteudo, cfg)
            return

        if cfg.get("anti_mencoes"):


            usuarios_unicos = {m.id for m in message.mentions}
            cargos_unicos = {r.id for r in message.role_mentions}
            total_mencoes = len(usuarios_unicos) + len(cargos_unicos)
            if total_mencoes >= cfg.get("anti_mencoes_limite", 8):
                await self._acao(message, "Menções em massa", f"{total_mencoes} menções únicas", cfg)
                return


        if cfg.get("anti_emojis"):
            total_emojis = len(REGEX_EMOJI_CUSTOM.findall(conteudo)) + len(REGEX_EMOJI_UNICODE.findall(conteudo))
            if total_emojis >= cfg.get("anti_emojis_limite", 10):
                await self._acao(message, "Excesso de emojis", f"{total_emojis} emojis", cfg)
                return


        norm = " ".join(conteudo.casefold().split())   # "A", "a " e "a" contam como a mesma mensagem
        historico = self.historico_msgs[chave]
        intervalo = cfg.get("anti_spam_intervalo", 5)
        janela_flood = cfg.get("anti_flood_janela", FLOOD_JANELA_PADRAO)

        # esquece o que já saiu das janelas de tempo
        while historico and agora - historico[0][0] > max(intervalo, janela_flood):
            historico.popleft()
        historico.append((agora, norm, message.channel.id, message.id))

        motivo = None
        rajada = []

        if cfg.get("anti_spam"):
            limite = cfg.get("anti_spam_limite", 5)
            recentes = [e for e in historico if agora - e[0] <= intervalo]
            if len(recentes) >= limite:
                motivo = "Spam detectado (muitas mensagens em pouco tempo)"
                rajada = recentes

        if motivo is None and cfg.get("anti_flood") and norm:
            limite_flood = cfg.get("anti_flood_limite", 3)
            ultimas = list(historico)[-limite_flood:]
            if (
                len(ultimas) >= limite_flood
                and all(agora - e[0] <= janela_flood for e in ultimas)
                and len({e[1] for e in ultimas}) == 1
            ):
                motivo = "Flood detectado (mensagens repetidas)"
                rajada = ultimas

        if motivo is not None:
            # marca o castigo ANTES de qualquer await: as mensagens que chegarem enquanto o
            # bot ainda está apagando já caem na regra do castigo lá em cima
            self.castigo_ate[chave] = agora + FLOOD_CASTIGO_SEGUNDOS
            historico.clear()

            # apaga também as mensagens ANTERIORES da rajada (antes só a última era apagada)
            por_canal = defaultdict(list)
            for _, _, canal_id, msg_id in rajada:
                if msg_id != message.id:
                    por_canal[canal_id].append(msg_id)
            for canal_id, ids in por_canal.items():
                await self._apagar_ids(canal_id, ids)

            await self._acao(message, f"{motivo} — {len(rajada)} mensagem(ns) removida(s)", conteudo, cfg)
            return


    automod_group = app_commands.Group(name="automod", description="Configurações do sistema de AutoMod.",
                                        default_permissions=discord.Permissions(manage_guild=True))

    @automod_group.command(name="status", description="Mostra a configuração atual do AutoMod.")
    async def automod_status(self, interaction: discord.Interaction):
        cfg = mu.get_automod(interaction.guild_id)
        linhas = [
            f"**Ativo:** {'✅' if cfg['ativo'] else '❌'}",
            f"**Anti-spam:** {'✅' if cfg['anti_spam'] else '❌'} ({cfg['anti_spam_limite']} msgs / {cfg['anti_spam_intervalo']}s)",
            f"**Anti-flood:** {'✅' if cfg['anti_flood'] else '❌'} ({cfg['anti_flood_limite']} repetidas em {cfg.get('anti_flood_janela', FLOOD_JANELA_PADRAO)}s)",
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
        app_commands.Choice(name="Janela em segundos (anti-flood)", value="anti_flood_janela"),
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
