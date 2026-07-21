import discord
from discord.ext import commands, tasks
import os
from datetime import datetime, timezone

from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Quarentena por inatividade
#  Arquivo: cogs/demote.py
#  Comandos:
#    !demotar @pessoa [motivo]   -> coloca o jogador em quarentena
#    !fecharquarentena [aprovado] -> fecha o canal (uso dentro do canal de quarentena)
#
#  Fluxo atual:
#    1) !demotar @pessoa -> expulsa a pessoa NA HORA e manda uma DM avisando.
#
#  Os comandos !fecharquarentena / !tirardemote e a checagem automática de
#  expiração continuam aqui, mas só entram em ação se ainda existir alguma
#  quarentena antiga registrada em data/quarentena.json — o fluxo novo não
#  cria mais quarentenas.
# ─────────────────────────────────────────────

# ───────────────── CONFIGURAÇÕES (preencha os IDs do seu servidor) ─────────────────
STAFF_ROLE_IDS = [
    1529150684296122438,   # Sub-Dono
    1529241192183627947,   # Tag de Staff
]                                             # cargos que enxergam os canais de quarentena

# Dono do Clube não é mais um cargo — é uma pessoa específica, então é
# mencionada separadamente (por ID de usuário) junto com os cargos acima.
DONO_CLUBE_USER_ID = 1487452210605588592

MEMBRO_ROLE_ID = 0                           # não há cargo de "Membro" no servidor — deixado em 0,
                                              # então essa etapa é simplesmente pulada.

QUARENTENA_ROLE_ID = 0                       # deixado em 0 -> o bot procura um cargo chamado
                                              # "Quarentena" e, se não existir, cria um
                                              # automaticamente (sem nenhuma permissão).

QUARENTENA_CATEGORY_NAME = "🔒 Quarentena"
DIAS_QUARENTENA = 7
INTERVALO_VERIFICACAO_MINUTOS = 30           # de quanto em quanto tempo o bot checa expiração

LOG_CHANNEL_ID = 1529234118557306971         # canal onde o bot manda o log de tudo que faz aqui

DATA_FILE = "data/quarentena.json"

MENSAGEM_QUARENTENA = (
    "Olá! Você entrou em quarentena por inatividade.\n\n"
    "Durante nosso período de avaliação, não identificamos atividade suficiente da sua "
    "parte. Para manter o clube ativo, jogadores inativos passam por esta etapa antes de "
    "uma remoção definitiva.\n\n"
    "Caso deseje continuar fazendo parte da **Ignition RL**, basta responder neste canal "
    "dentro de **7 dias**.\n\n"
    "Se não houver nenhuma resposta nesse período, você será removido automaticamente do clube."
)  # legado — não é mais usada pelo !demotar, só fica aqui pra não quebrar quarentenas antigas

MENSAGEM_REMOCAO_FINAL = (
    "Olá! Você foi removido da **Ignition RL** porque não houve nenhuma interação "
    "durante o período de quarentena de 7 dias.\n\n"
    "Caso queira receber uma nova oportunidade para voltar ao clube, entre em contato com "
    "**ravokes** pelo Discord. Após a análise da Staff, você poderá receber uma nova chance "
    "para demonstrar sua atividade."
)  # legado — usada só pela checagem automática de quarentenas antigas que ainda estejam em aberto

MENSAGEM_EXPULSAO_DIRETA = (
    "Olá, tudo bem?\n\n"
    "Você foi removido porque estava inativo. Demos algumas oportunidades para que voltasse "
    "a participar, mas não houve demonstração de atividade."
)


# ── Helpers de leitura/escrita ──────────────────────────────────────────────
def ler_dados() -> dict:
    return ler_json(DATA_FILE, {"ativos": {}})


def salvar_dados(dados: dict):
    salvar_json(DATA_FILE, dados)


class Demote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not os.path.exists(DATA_FILE):
            salvar_dados({"ativos": {}})
        self.checar_expiracoes.start()

    def cog_unload(self):
        self.checar_expiracoes.cancel()

    # ── Envia uma mensagem de log no canal de logs ──────────────────────────
    async def enviar_log(self, title: str, description: str, color: int = 0x5865F2, fields: list = None):
        canal = self.bot.get_channel(LOG_CHANNEL_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(LOG_CHANNEL_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal = None
        if canal is None:
            print(f"[DEMOTE] ⚠️ Canal de logs ({LOG_CHANNEL_ID}) não encontrado.")
            return

        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
        if fields:
            for nome, valor in fields:
                embed.add_field(name=nome, value=valor, inline=False)
        embed.set_footer(text="Sistema de Quarentena")

        try:
            await canal.send(embed=embed)
        except discord.Forbidden:
            print(f"[DEMOTE] ⚠️ Sem permissão para mandar mensagem no canal de logs ({LOG_CHANNEL_ID}).")
        except discord.HTTPException as e:
            print(f"[DEMOTE] ⚠️ Falha ao mandar log: {e}")

    # ── Envia a DM de expulsão por inatividade pro membro ───────────────────
    async def enviar_dm_expulsao(self, membro: discord.Member) -> bool:
        """Manda a mensagem de expulsão por DM. Retorna True se conseguiu enviar."""
        embed = discord.Embed(
            title="🔻 Você foi removido(a) do clube",
            description=MENSAGEM_EXPULSAO_DIRETA,
            color=0xED4245,
        )
        embed.set_footer(text="Ignition RL")
        try:
            await membro.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    # ── Restaura os cargos que o membro tinha antes de entrar em quarentena ─
    async def restaurar_cargos(self, guild: discord.Guild, membro: discord.Member, info: dict) -> list:
        """Remove o cargo Quarentena e devolve todos os cargos salvos. Retorna a lista de cargos restaurados."""
        cargo_quarentena = await self.obter_cargo_quarentena(guild)
        if cargo_quarentena in membro.roles:
            try:
                await membro.remove_roles(cargo_quarentena, reason="Quarentena encerrada — membro voltou a ficar ativo")
            except discord.Forbidden:
                pass

        cargos_para_restaurar = []
        for role_id in info.get("cargos_removidos", []):
            cargo = guild.get_role(role_id)
            if cargo is not None and cargo not in membro.roles:
                cargos_para_restaurar.append(cargo)

        if cargos_para_restaurar:
            try:
                await membro.add_roles(*cargos_para_restaurar, reason="Cargos restaurados após saída da quarentena")
            except discord.Forbidden:
                print(f"[DEMOTE] ⚠️ Sem permissão para restaurar todos os cargos de {membro}.")

        return cargos_para_restaurar

    # ── Pega (ou cria) o cargo Quarentena ───────────────────────────────────
    async def obter_cargo_quarentena(self, guild: discord.Guild) -> discord.Role:
        if QUARENTENA_ROLE_ID:
            cargo = guild.get_role(QUARENTENA_ROLE_ID)
            if cargo:
                return cargo

        cargo = discord.utils.get(guild.roles, name="Quarentena")
        if cargo:
            return cargo

        # Cria o cargo sem nenhuma permissão (inclusive sem "Ver canais"),
        # assim ele não concede acesso a nada por conta própria.
        cargo = await guild.create_role(
            name="Quarentena",
            permissions=discord.Permissions.none(),
            color=discord.Color.dark_gray(),
            reason="Cargo de quarentena criado automaticamente pelo bot",
        )
        print(f"[DEMOTE] ✅ Cargo 'Quarentena' criado em {guild.name}.")
        return cargo

    # ── !demotar @pessoa ────────────────────────────────────────────────────
    @commands.command(name="demotar")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def demotar(self, ctx: commands.Context, membro: discord.Member = None, *, motivo: str = None):
        """Expulsa um jogador do servidor por inatividade, avisando por DM antes.

        Uso:
          !demotar @pessoa               -> usa o motivo padrão (inatividade)
          !demotar @pessoa Sumiu 3 meses -> usa um motivo customizado
        """
        if membro is None:
            await ctx.send("⚠️ Uso correto: `!demotar @pessoa`", delete_after=6)
            return

        if membro == ctx.author:
            await ctx.send("❌ Você não pode usar esse comando em si mesmo.", delete_after=6)
            return

        if membro.bot:
            await ctx.send("❌ Não é possível expulsar um bot com esse comando.", delete_after=6)
            return

        if membro.guild_permissions.administrator:
            await ctx.send("❌ Não é possível expulsar um administrador.", delete_after=6)
            return

        if membro.top_role >= ctx.guild.me.top_role:
            await ctx.send(
                "❌ Não consigo gerenciar esse membro — o cargo dele é igual ou "
                "maior que o meu cargo mais alto.",
                delete_after=8
            )
            return

        motivo_final = motivo or "Inatividade"

        # Manda a DM antes de expulsar — depois que o kick acontece o bot só
        # consegue mandar DM se ainda tiver um servidor em comum com a pessoa.
        dm_enviada = await self.enviar_dm_expulsao(membro)

        try:
            await ctx.guild.kick(membro, reason=f"Demote por inatividade — ação de {ctx.author} ({motivo_final})")
        except discord.Forbidden:
            await ctx.send("❌ Não tenho permissão para expulsar esse membro.", delete_after=8)
            return

        confirmacao = discord.Embed(
            title="🔻 Jogador expulso por inatividade",
            description=f"**{membro}** foi expulso(a) do servidor.",
            color=0xED4245,
        )
        confirmacao.add_field(name="Motivo", value=motivo_final, inline=False)
        confirmacao.add_field(
            name="Aviso por DM",
            value="✅ Enviado" if dm_enviada else "⚠️ Não foi possível enviar (DM fechada)",
            inline=False,
        )
        await ctx.send(embed=confirmacao)
        print(f"[DEMOTE] 🔻 {membro} expulso por {ctx.author}. Motivo: {motivo_final}")

        await self.enviar_log(
            title="🔻 Membro expulso por inatividade",
            description=f"{membro.mention} (`{membro}` / `{membro.id}`) foi expulso(a) por {ctx.author.mention}.",
            color=0xED4245,
            fields=[
                ("Motivo", motivo_final),
                ("Aviso por DM", "✅ Enviado" if dm_enviada else "⚠️ Não foi possível enviar"),
            ],
        )

    @demotar.error
    async def demotar_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Expulsar Membros** para usar este comando.", delete_after=6)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado. Marque a pessoa com `@`.", delete_after=6)
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"❌ Preciso das permissões: {', '.join(error.missing_permissions)}", delete_after=8)

    # ── !fecharquarentena [aprovado] — fecha o canal atual ──────────────────
    @commands.command(name="fecharquarentena", aliases=["fechardemote"])
    @commands.has_permissions(kick_members=True)
    async def fecharquarentena(self, ctx: commands.Context, decisao: str = None):
        """Encerra a quarentena aberta no canal atual.

        Uso:
          !fecharquarentena           -> só fecha e apaga o canal
          !fecharquarentena aprovado  -> restaura o cargo de Membro, remove a
                                         Quarentena e apaga o canal
        """
        dados = ler_dados()
        user_id_alvo = None
        for uid, info in dados["ativos"].items():
            if info["channel_id"] == ctx.channel.id:
                user_id_alvo = uid
                break

        if user_id_alvo is None:
            await ctx.send("⚠️ Este comando só funciona dentro de um canal de quarentena.", delete_after=6)
            return

        guild = ctx.guild
        membro = guild.get_member(int(user_id_alvo))
        aprovado = (decisao or "").strip().lower() == "aprovado"
        info = dados["ativos"][user_id_alvo]
        cargos_restaurados = []

        if aprovado and membro:
            cargos_restaurados = await self.restaurar_cargos(guild, membro, info)
            try:
                await membro.send(
                    "✅ Sua quarentena foi encerrada e você continua fazendo parte da "
                    "**Ignition RL**. Bem-vindo(a) de volta à atividade!"
                )
            except discord.Forbidden:
                pass

        del dados["ativos"][user_id_alvo]
        salvar_dados(dados)

        await ctx.send("🔒 Fechando este canal em 3 segundos...")

        nomes_cargos = ", ".join(r.name for r in cargos_restaurados) if cargos_restaurados else "—"
        await self.enviar_log(
            title="✅ Quarentena encerrada" if aprovado else "🔒 Canal de quarentena fechado",
            description=(
                f"A quarentena de **{membro or info.get('user_name', user_id_alvo)}** "
                f"(`{user_id_alvo}`) foi encerrada por {ctx.author.mention}."
            ),
            color=0x57F287 if aprovado else 0x99AAB5,
            fields=[
                ("Decisão", "Aprovado — cargos restaurados" if aprovado else "Apenas fechado (sem restaurar cargos)"),
                ("Cargos restaurados", nomes_cargos) if aprovado else ("Canal", ctx.channel.name),
            ],
        )

        await ctx.channel.delete(reason=f"Quarentena encerrada por {ctx.author}")
        print(f"[DEMOTE] ✅ Quarentena de {membro or user_id_alvo} encerrada por {ctx.author} (aprovado={aprovado}).")

    @fecharquarentena.error
    async def fecharquarentena_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Expulsar Membros** para usar este comando.", delete_after=6)

    # ── !tirardemote @pessoa — tira a pessoa da quarentena de qualquer canal ─
    @commands.command(name="tirardemote", aliases=["tirarquarentena"])
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def tirardemote(self, ctx: commands.Context, membro: discord.Member = None):
        """Remove a quarentena de alguém, restaura os cargos e apaga o canal, de qualquer lugar do servidor.

        Uso:
          !tirardemote @pessoa
          !tirardemote Nick
        """
        if membro is None:
            await ctx.send("⚠️ Uso correto: `!tirardemote @pessoa` (ou o nick dela)", delete_after=6)
            return

        dados = ler_dados()
        user_id_alvo = str(membro.id)

        if user_id_alvo not in dados["ativos"]:
            await ctx.send(f"⚠️ **{membro}** não está em quarentena.", delete_after=6)
            return

        guild = ctx.guild
        info = dados["ativos"][user_id_alvo]

        cargos_restaurados = await self.restaurar_cargos(guild, membro, info)

        canal = self.bot.get_channel(info["channel_id"])

        del dados["ativos"][user_id_alvo]
        salvar_dados(dados)

        try:
            await membro.send(
                "✅ Sua quarentena foi encerrada e você continua fazendo parte da "
                "**Ignition RL**. Bem-vindo(a) de volta à atividade!"
            )
        except discord.Forbidden:
            pass

        if canal:
            try:
                await canal.delete(reason=f"Quarentena removida manualmente por {ctx.author}")
            except discord.Forbidden:
                pass

        nomes_cargos = ", ".join(r.name for r in cargos_restaurados) if cargos_restaurados else "—"

        confirmacao = discord.Embed(
            title="✅ Quarentena removida",
            description=f"**{membro}** saiu da quarentena e teve os cargos restaurados.",
            color=0x57F287,
        )
        confirmacao.add_field(name="Cargos restaurados", value=nomes_cargos, inline=False)
        await ctx.send(embed=confirmacao)
        print(f"[DEMOTE] ✅ Quarentena de {membro} removida manualmente por {ctx.author}.")

        await self.enviar_log(
            title="✅ Quarentena removida manualmente",
            description=(
                f"{membro.mention} (`{membro}` / `{membro.id}`) teve a quarentena removida "
                f"por {ctx.author.mention} usando `!tirardemote`."
            ),
            color=0x57F287,
            fields=[
                ("Cargos restaurados", nomes_cargos),
            ],
        )

    @tirardemote.error
    async def tirardemote_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você precisa da permissão **Expulsar Membros** para usar este comando.", delete_after=6)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado. Marque a pessoa com `@` ou use o nick certinho.", delete_after=6)
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"❌ Preciso das permissões: {', '.join(error.missing_permissions)}", delete_after=8)

    # ── Lógica central de expulsão reaproveitada pelo demote em massa ────────
    async def _executar_expulsao_individual(self, guild: discord.Guild, membro: discord.Member, motivo: str, executor: discord.abc.User):
        """Manda a DM de aviso e expulsa o membro na hora.
        Retorna (status, motivo_falha) onde status é "sucesso" ou "falha"."""
        if membro.top_role >= guild.me.top_role:
            return "falha", "cargo igual ou maior que o do bot"

        dm_enviada = await self.enviar_dm_expulsao(membro)

        try:
            await guild.kick(membro, reason=f"Demote em massa por inatividade — ação de {executor}")
        except discord.Forbidden:
            return "falha", "sem permissão pra expulsar"

        return "sucesso", ("DM não enviada (fechada)" if not dm_enviada else None)

    # ── Tira alguém da quarentena sem precisar de comando/canal (usado pelo !ativar) ──
    async def forcar_saida_quarentena(self, membro: discord.Member, motivo: str = "Marcado como ativo manualmente") -> bool:
        """Se o membro estiver em quarentena, restaura os cargos dele e apaga o canal.
        Retorna True se ele estava em quarentena (e foi tirado), False se não estava."""
        dados = ler_dados()
        info = dados["ativos"].get(str(membro.id))
        if info is None:
            return False

        guild = membro.guild
        await self.restaurar_cargos(guild, membro, info)

        canal = self.bot.get_channel(info["channel_id"])
        del dados["ativos"][str(membro.id)]
        salvar_dados(dados)

        if canal:
            try:
                await canal.delete(reason=motivo)
            except discord.Forbidden:
                pass

        try:
            await membro.send(
                "✅ Você foi marcado(a) como ativo(a) e sua quarentena foi encerrada. "
                "Bem-vindo(a) de volta à atividade na **Ignition RL**!"
            )
        except discord.Forbidden:
            pass

        await self.enviar_log(
            title="✅ Saída de quarentena (manual)",
            description=f"{membro.mention} (`{membro}` / `{membro.id}`) foi tirado da quarentena porque foi marcado como ativo manualmente.",
            color=0x57F287,
        )
        return True

    # ── Detecta resposta do jogador no canal de quarentena ──────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        prefixo = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else "!"
        if message.content.startswith(prefixo):
            return  # deixa comandos passarem normalmente

        dados = ler_dados()
        user_id_alvo = None
        for uid, info in dados["ativos"].items():
            if info["channel_id"] == message.channel.id:
                user_id_alvo = uid
                break

        if user_id_alvo is None:
            return

        # Só o próprio jogador cancela a contagem ao responder
        if str(message.author.id) != user_id_alvo:
            return

        info = dados["ativos"][user_id_alvo]
        if info["respondido"]:
            return

        info["respondido"] = True
        salvar_dados(dados)

        # Membro ficou ativo -> restaura automaticamente todos os cargos que ele tinha antes
        cargos_restaurados = await self.restaurar_cargos(message.guild, message.author, info)

        mencoes = [
            role.mention for rid in STAFF_ROLE_IDS
            if (role := message.guild.get_role(rid)) is not None
        ]
        dono = message.guild.get_member(DONO_CLUBE_USER_ID)
        if dono:
            mencoes.append(dono.mention)
        mencao = " ".join(mencoes) if mencoes else "Staff"

        nomes_cargos = ", ".join(r.name for r in cargos_restaurados) if cargos_restaurados else "Nenhum cargo para restaurar"

        aviso = discord.Embed(
            title="✅ Jogador respondeu na quarentena",
            description=(
                f"**{message.author}** respondeu dentro do prazo. O contador de "
                f"{DIAS_QUARENTENA} dias foi **cancelado** e os cargos dele(a) foram "
                f"**restaurados automaticamente**.\n\n"
                f"Cargos restaurados: {nomes_cargos}\n\n"
                f"Usem `!fecharquarentena aprovado` para encerrar e fechar este canal."
            ),
            color=0x57F287,
        )
        await message.channel.send(content=mencao, embed=aviso)
        print(f"[DEMOTE] ✅ {message.author} respondeu na quarentena — contador cancelado e cargos restaurados.")

        await self.enviar_log(
            title="✅ Membro voltou a ficar ativo",
            description=(
                f"{message.author.mention} (`{message.author}` / `{message.author.id}`) respondeu "
                f"no canal de quarentena e teve os cargos restaurados automaticamente."
            ),
            color=0x57F287,
            fields=[
                ("Cargos restaurados", nomes_cargos),
                ("Canal", message.channel.mention),
            ],
        )

    # ── Se o canal de quarentena for apagado (manualmente ou por permissão), encerra a quarentena ──
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        dados = ler_dados()
        user_id_alvo = None
        for uid, info in dados["ativos"].items():
            if info["channel_id"] == channel.id:
                user_id_alvo = uid
                break

        if user_id_alvo is None:
            return  # não era um canal de quarentena controlado pelo bot

        info = dados["ativos"][user_id_alvo]
        del dados["ativos"][user_id_alvo]
        salvar_dados(dados)

        print(f"[DEMOTE] 🗑️ Canal de quarentena de {info.get('user_name', user_id_alvo)} foi apagado — quarentena encerrada.")

        await self.enviar_log(
            title="🗑️ Canal de quarentena apagado",
            description=(
                f"O canal `#{channel.name}` foi apagado e a quarentena de "
                f"**{info.get('user_name', user_id_alvo)}** (`{user_id_alvo}`) foi encerrada automaticamente.\n\n"
                f"⚠️ Os cargos removidos **não** foram restaurados — use um comando de cargo manual "
                f"se quiser devolvê-los."
            ),
            color=0x99AAB5,
            fields=[
                ("Motivo original", info.get("motivo", "Inatividade")),
                ("Cargos salvos (não restaurados)",
                 ", ".join(str(rid) for rid in info.get("cargos_removidos", [])) or "—"),
            ],
        )

    # ── Checagem periódica de expiração (a cada N minutos) ───────────────────
    @tasks.loop(minutes=INTERVALO_VERIFICACAO_MINUTOS)
    async def checar_expiracoes(self):
        dados = ler_dados()
        agora = datetime.now(timezone.utc)
        alterou = False

        for uid, info in list(dados["ativos"].items()):
            try:
                if info.get("respondido"):
                    continue

                expira_em = datetime.fromisoformat(info["expira_em"])
                if agora < expira_em:
                    continue

                guild = self.bot.get_guild(info["guild_id"])
                if guild is None:
                    continue

                membro = guild.get_member(int(uid))

                # Envia a DM final antes de expulsar
                if membro:
                    try:
                        embed = discord.Embed(
                            title="🔻 Remoção do Clube",
                            description=MENSAGEM_REMOCAO_FINAL,
                            color=0xED4245,
                        )
                        embed.set_footer(text="Ignition RL")
                        await membro.send(embed=embed)
                    except discord.Forbidden:
                        pass

                    try:
                        await guild.kick(membro, reason="Sem resposta durante os 7 dias de quarentena")
                    except discord.Forbidden:
                        print(f"[DEMOTE] ❌ Sem permissão para expulsar {membro} após expiração da quarentena.")

                del dados["ativos"][uid]
                alterou = True
                salvar_dados(dados)  # salva antes de apagar o canal, pra não duplicar o log do listener de canal apagado

                canal = self.bot.get_channel(info["channel_id"])
                if canal:
                    try:
                        await canal.delete(reason="Quarentena expirada — jogador expulso automaticamente")
                    except discord.Forbidden:
                        pass

                print(f"[DEMOTE] 🔻 {info.get('user_name', uid)} expulso automaticamente após {DIAS_QUARENTENA} dias sem resposta.")

                await self.enviar_log(
                    title="🔻 Expulsão automática após quarentena",
                    description=(
                        f"**{info.get('user_name', uid)}** (`{uid}`) foi expulso(a) automaticamente "
                        f"por não responder em {DIAS_QUARENTENA} dias."
                    ),
                    color=0xED4245,
                    fields=[
                        ("Motivo original", info.get("motivo", "Inatividade")),
                        ("Cargos que ele(a) tinha (não restaurados)",
                         ", ".join(str(rid) for rid in info.get("cargos_removidos", [])) or "—"),
                    ],
                )
            except Exception as e:
                # Um registro malformado (ex: 'expira_em' ausente/inválido, dado
                # legado corrompido) não pode derrubar o loop pra sempre — isso
                # pararia a expulsão automática de quarentena para TODO MUNDO,
                # não só para esse registro.
                print(f"[DEMOTE] ⚠️ Erro ao processar quarentena de {uid}: {e}")

        if alterou:
            salvar_dados(dados)

    @checar_expiracoes.before_loop
    async def antes_de_checar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Demote(bot))
