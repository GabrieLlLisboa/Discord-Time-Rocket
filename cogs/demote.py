import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Demoção por inatividade
#  Arquivo: cogs/demote.py
#  Comandos: !demotar @pessoa | !fechardemote
#  Fluxo:
#    1) !demotar @pessoa -> expulsa e manda DM padrão
#    2) Pessoa responde "QUEROVOLTAR" no privado
#    3) Bot cria um canal (categoria "Retornos") no servidor
#    4) Tudo que a equipe escreve nesse canal vira DM pra pessoa
#       e tudo que a pessoa manda de volta no privado aparece no canal
# ─────────────────────────────────────────────

DATA_FILE      = "data/demotados.json"
CATEGORY_NAME  = "📋 Retornos"

MENSAGEM_DEMOCAO_PADRAO = (
    "Olá! Você foi removido do clube **TryHarders RL** devido à sua inatividade.\n\n"
    "Recentemente, realizamos um período de avaliação de atividade para identificar "
    "quais jogadores estavam participando do clube. Durante esse período, não "
    "registramos atividade suficiente da sua parte.\n\n"
    "Manter uma comunidade ativa é muito importante para o crescimento e a organização "
    "do clube. Por isso, foi necessário realizar essa remoção.\n\n"
    "Caso queira voltar e ter uma segunda oportunidade para demonstrar sua atividade, "
    "basta responder a esta mensagem com a palavra:\n\n"
    "**QUEROVOLTAR**\n\n"
    "Assim, sua solicitação será analisada pela equipe. Esperamos ver você de volta em breve!"
)

INSTRUCOES_RETORNO = (
    "Caso queira voltar e ter uma segunda oportunidade, basta responder a esta "
    "mensagem com a palavra:\n\n"
    "**QUEROVOLTAR**\n\n"
    "Assim, sua solicitação será analisada pela equipe. Esperamos ver você de volta em breve!"
)


def montar_mensagem_democao(motivo: str = None) -> str:
    """Monta o texto da DM de demoção. Usa o texto padrão, ou um customizado se `motivo` for informado."""
    if not motivo:
        return MENSAGEM_DEMOCAO_PADRAO
    return (
        f"Olá! Você foi removido do clube **TryHarders RL**.\n\n"
        f"**Motivo:** {motivo}\n\n"
        f"{INSTRUCOES_RETORNO}"
    )


# ── Helpers de leitura/escrita (mesmo padrão do cogs/backup.py) ────────────────
def ler_dados() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"aguardando": {}, "tickets": {}}


def salvar_dados(dados: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


class Demote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not os.path.exists(DATA_FILE):
            salvar_dados({"aguardando": {}, "tickets": {}})

    # ── !demotar @pessoa ────────────────────────────────────────────────────
    @commands.command(name="demotar")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def demotar(self, ctx: commands.Context, membro: discord.Member = None, *, motivo: str = None):
        """Expulsa um membro e envia a mensagem de demoção no privado.

        Uso:
          !demotar @pessoa               -> usa a mensagem padrão (inatividade)
          !demotar @pessoa Sumiu 3 meses -> usa um motivo customizado no lugar do texto padrão
        """
        if membro is None:
            await ctx.send("⚠️ Uso correto: `!demotar @pessoa`", delete_after=6)
            return

        if membro == ctx.author:
            await ctx.send("❌ Você não pode usar esse comando em si mesmo.", delete_after=6)
            return

        if membro.bot:
            await ctx.send("❌ Não é possível demotar um bot.", delete_after=6)
            return

        if membro.guild_permissions.administrator:
            await ctx.send("❌ Não é possível demotar um administrador do servidor.", delete_after=6)
            return

        if membro.top_role >= ctx.guild.me.top_role:
            await ctx.send(
                "❌ Não consigo expulsar esse membro — o cargo dele é igual ou "
                "maior que o meu cargo mais alto.",
                delete_after=8
            )
            return

        # Envia a DM ANTES de expulsar (depois de sair, pode não ser mais possível)
        dm_enviada = True
        embed = discord.Embed(
            title="🔻 Remoção do Clube",
            description=montar_mensagem_democao(motivo),
            color=0xED4245
        )
        embed.set_footer(text="TryHarders RL")

        try:
            await membro.send(embed=embed)
        except discord.Forbidden:
            dm_enviada = False

        motivo_auditoria = motivo or "Inatividade"
        try:
            await ctx.guild.kick(membro, reason=f"{motivo_auditoria} — ação de {ctx.author}")
        except discord.Forbidden:
            await ctx.send("❌ Não tenho permissão para expulsar esse membro.", delete_after=6)
            return

        # Marca o usuário como "aguardando QUEROVOLTAR"
        dados = ler_dados()
        dados["aguardando"][str(membro.id)] = {
            "guild_id":  ctx.guild.id,
            "user_name": str(membro),
            "motivo":    motivo or "Inatividade",
            "kicked_at": datetime.now(timezone.utc).isoformat(),
        }
        salvar_dados(dados)

        confirmacao = discord.Embed(
            title="✅ Membro demovido",
            description=f"**{membro}** foi removido do servidor.",
            color=0x57F287
        )
        confirmacao.add_field(
            name="DM enviada?",
            value="Sim ✅" if dm_enviada else "Não ❌ (privado fechado — a pessoa não poderá pedir para voltar por lá)",
            inline=False
        )
        await ctx.send(embed=confirmacao)
        print(f"[DEMOTE] ✅ {membro} demovido por {ctx.author} (DM enviada: {dm_enviada}).")

    @demotar.error
    async def demotar_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Expulsar Membros** para usar este comando.", delete_after=6)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado. Marque a pessoa com `@`.", delete_after=6)

    # ── !fechardemote — fecha o canal de retorno atual ──────────────────────
    @commands.command(name="fechardemote")
    @commands.has_permissions(kick_members=True)
    async def fechardemote(self, ctx: commands.Context, *, mensagem_final: str = None):
        """Encerra o atendimento de retorno aberto no canal atual."""
        dados = ler_dados()
        user_id_alvo = None
        for uid, info in dados["tickets"].items():
            if info["channel_id"] == ctx.channel.id:
                user_id_alvo = uid
                break

        if user_id_alvo is None:
            await ctx.send("⚠️ Este comando só funciona dentro de um canal de retorno.", delete_after=6)
            return

        usuario = self.bot.get_user(int(user_id_alvo))
        if usuario is None:
            try:
                usuario = await self.bot.fetch_user(int(user_id_alvo))
            except discord.NotFound:
                usuario = None

        texto_final = mensagem_final or (
            "Seu atendimento foi encerrado pela equipe do TryHarders RL. "
            "Se precisar, você pode nos procurar novamente."
        )
        if usuario:
            try:
                await usuario.send(f"🔒 **{texto_final}**")
            except discord.Forbidden:
                pass

        del dados["tickets"][user_id_alvo]
        salvar_dados(dados)

        await ctx.send("🔒 Encerrando este atendimento em 3 segundos...")
        await asyncio.sleep(3)
        await ctx.channel.delete(reason=f"Atendimento de retorno encerrado por {ctx.author}")
        print(f"[DEMOTE] ✅ Atendimento com {usuario or user_id_alvo} encerrado por {ctx.author}.")

    @fechardemote.error
    async def fechardemote_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Expulsar Membros** para usar este comando.", delete_after=6)

    # ── Cria o canal de retorno quando a pessoa manda QUEROVOLTAR ───────────
    async def criar_canal_retorno(self, autor: discord.User, dados: dict):
        info  = dados["aguardando"][str(autor.id)]
        guild = self.bot.get_guild(info["guild_id"])
        if guild is None:
            return

        categoria = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if categoria is None:
            categoria = await guild.create_category(CATEGORY_NAME)

        nome_canal = f"retorno-{autor.name}".lower().replace(" ", "-")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me:            discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            reason=f"Pedido de retorno de {autor}"
        )

        embed = discord.Embed(
            title="🔁 Pedido de retorno",
            description=(
                f"**{autor}** (`{autor.id}`) foi removido — motivo: **{info.get('motivo', 'Inatividade')}** — e "
                f"respondeu **QUEROVOLTAR** no privado.\n\n"
                f"Tudo que a equipe escrever **neste canal** será enviado no privado "
                f"da pessoa, e as respostas dela aparecerão aqui automaticamente.\n\n"
                f"Use `!fechardemote` (opcionalmente seguido de uma mensagem final) "
                f"para encerrar este atendimento."
            ),
            color=0x5865F2
        )
        embed.set_thumbnail(url=autor.display_avatar.url)
        await canal.send(embed=embed)

        dados["tickets"][str(autor.id)] = {
            "channel_id": canal.id,
            "guild_id":   guild.id,
            "user_name":  str(autor),
        }
        del dados["aguardando"][str(autor.id)]
        salvar_dados(dados)

        try:
            await autor.send("✅ Recebemos seu pedido! Nossa equipe vai analisar e falar com você por aqui em breve.")
        except discord.Forbidden:
            pass

        print(f"[DEMOTE] ✅ Canal {nome_canal} criado para o retorno de {autor}.")

    # ── Ponte DM <-> canal ───────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        prefixo = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else "!"

        # Mensagem recebida no privado do bot
        if isinstance(message.channel, discord.DMChannel):
            dados   = ler_dados()
            user_id = str(message.author.id)

            # Já existe atendimento aberto -> encaminha pro canal
            if user_id in dados["tickets"]:
                canal = self.bot.get_channel(dados["tickets"][user_id]["channel_id"])
                if canal is None:
                    return
                if message.content:
                    embed = discord.Embed(description=message.content, color=0x2B2D31)
                    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                    await canal.send(embed=embed)
                for anexo in message.attachments:
                    await canal.send(anexo.url)
                return

            # Está aguardando e mandou a palavra-chave
            if user_id in dados["aguardando"] and message.content.strip().upper() == "QUEROVOLTAR":
                await self.criar_canal_retorno(message.author, dados)
                return

        # Mensagem em um canal do servidor -> checa se é um canal de retorno
        else:
            if message.content.startswith(prefixo):
                return  # deixa comandos (ex: !fechardemote) passarem sem virar DM

            dados         = ler_dados()
            user_id_alvo  = None
            for uid, info in dados["tickets"].items():
                if info["channel_id"] == message.channel.id:
                    user_id_alvo = uid
                    break

            if user_id_alvo is None:
                return

            usuario = self.bot.get_user(int(user_id_alvo))
            if usuario is None:
                try:
                    usuario = await self.bot.fetch_user(int(user_id_alvo))
                except discord.NotFound:
                    return

            try:
                if message.content:
                    await usuario.send(f"**Equipe TryHarders RL:** {message.content}")
                for anexo in message.attachments:
                    await usuario.send(anexo.url)
                await message.add_reaction("✅")
            except discord.Forbidden:
                await message.channel.send(
                    "⚠️ Não foi possível entregar a mensagem — a pessoa bloqueou o bot ou fechou as DMs."
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(Demote(bot))
