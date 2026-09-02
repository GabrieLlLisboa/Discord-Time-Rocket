import discord
from discord.ext import commands

# ─────────────────────────────────────────────
#  Cog: Notificações
#  Arquivo: cogs/notifications.py
#  Comando: !notificacoes
#  Select menu com toggle de cargo
# ─────────────────────────────────────────────

CARGOS_NOTIFICACAO = {
    "amistosos": {
        "id":    1514788829695971378,
        "label": "Notificação Amistosos",
        "emoji": "⚽",
        "desc":  "Seja avisado sobre amistosos.",
    },
    "anuncios": {
        "id":    1514788861090205839,
        "label": "Notificação Anúncios",
        "emoji": "📢",
        "desc":  "Receba os anúncios do servidor.",
    },
    "novo_jogador": {
        "id":    1514788887300538531,
        "label": "Notificação Novo Jogador",
        "emoji": "🆕",
        "desc":  "Saiba quando um novo jogador entrar.",
    },
    "vitoria": {
        "id":    1514788925795733682,
        "label": "Notificação Vitória",
        "emoji": "🏆",
        "desc":  "Comemore cada vitória do time!",
    },
    "video_novo": {
        "id":    1515158913555894443,
        "label": "Notificação Vídeo Novo",
        "emoji": "🎵",
        "desc":  "Seja avisado quando sair vídeo novo no TikTok.",
    },
}


# ── Select Menu ────────────────────────────────────────────────────────────────
class NotificacaoSelect(discord.ui.Select):
    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label=dados["label"],
                description=dados["desc"],
                emoji=dados["emoji"],
                value=chave,
            )
            for chave, dados in CARGOS_NOTIFICACAO.items()
        ]
        super().__init__(
            custom_id="notificacao_select",
            placeholder="🔔 Selecione as notificações que deseja...",
            min_values=1,
            max_values=len(opcoes),
            options=opcoes,
        )

    async def callback(self, interaction: discord.Interaction):
        membro   = interaction.user
        guild    = interaction.guild
        adicionados = []
        removidos   = []

        for chave in self.values:
            dados = CARGOS_NOTIFICACAO[chave]
            cargo = guild.get_role(dados["id"])

            if cargo is None:
                continue

            if cargo in membro.roles:
                await membro.remove_roles(cargo, reason="Toggle notificação")
                removidos.append(f"{dados['emoji']} {dados['label']}")
            else:
                await membro.add_roles(cargo, reason="Toggle notificação")
                adicionados.append(f"{dados['emoji']} {dados['label']}")

        # Monta resposta
        linhas = []
        if adicionados:
            linhas.append("✅ **Ativados:**\n" + "\n".join(f"  {c}" for c in adicionados))
        if removidos:
            linhas.append("🔕 **Removidos:**\n" + "\n".join(f"  {c}" for c in removidos))

        await interaction.response.send_message(
            "\n\n".join(linhas) if linhas else "Nenhuma alteração feita.",
            ephemeral=True
        )


# ── View ───────────────────────────────────────────────────────────────────────
class NotificacaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(NotificacaoSelect())


# ── Cog ───────────────────────────────────────────────────────────────────────
class Notifications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="notificacoes")
    @commands.has_permissions(administrator=True)
    async def notificacoes(self, ctx: commands.Context):
        """Envia o painel de seleção de notificações no canal atual."""
        await ctx.message.delete()

        embed = discord.Embed(
            title="🔔 Notificações",
            description=(
                "Selecione abaixo quais notificações deseja receber.\n"
                "Clique novamente em uma opção já ativa para **remover**.\n\n"
                "⚽ **Amistosos** — Avisos de partidas amistosas\n"
                "📢 **Anúncios** — Novidades e comunicados\n"
                "🆕 **Novo Jogador** — Entrada de novos membros\n"
                "🏆 **Vitória** — Comemorações de vitória\n"
                "🎵 **Vídeo Novo** — Novos vídeos no TikTok"
            ),
            color=0x57F287
        )
        embed.set_footer(text="Você pode ativar ou desativar a qualquer momento.")

        await ctx.send(embed=embed, view=NotificacaoView())
        print(f"[NOTIF] ✅ Painel de notificações enviado em #{ctx.channel.name} por {ctx.author}.")

    @notificacoes.error
    async def notificacoes_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa ser **Administrador** para usar este comando.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
