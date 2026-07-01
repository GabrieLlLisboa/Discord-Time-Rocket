import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────────
#  Cog: Quarentena por inatividade
#  Arquivo: cogs/demote.py
#  Comandos:
#    !demotar @pessoa [motivo]   -> coloca o jogador em quarentena
#    !fecharquarentena [aprovado] -> fecha o canal (uso dentro do canal de quarentena)
#
#  Fluxo:
#    1) !demotar @pessoa -> remove cargo Membro, dá cargo Quarentena,
#       cria canal privado e manda a mensagem de aviso nele.
#    2) Contador de 7 dias começa.
#    3) Se a pessoa responder no canal -> contador cancela e a staff é avisada.
#    4) Se passarem 7 dias sem resposta -> kick automático, canal apagado,
#       DM final é enviada.
# ─────────────────────────────────────────────

# ───────────────── CONFIGURAÇÕES (preencha os IDs do seu servidor) ─────────────────
STAFF_ROLE_IDS = [
    1511895253777649704,   # Dono do Clube
    1511894837790769204,   # Administrador
]                                             # cargos que enxergam os canais de quarentena

MEMBRO_ROLE_ID = 0                           # não há cargo de "Membro" no servidor — deixado em 0,
                                              # então essa etapa é simplesmente pulada.

QUARENTENA_ROLE_ID = 0                       # deixado em 0 -> o bot procura um cargo chamado
                                              # "Quarentena" e, se não existir, cria um
                                              # automaticamente (sem nenhuma permissão).

QUARENTENA_CATEGORY_NAME = "🔒 Quarentena"
DIAS_QUARENTENA = 7
INTERVALO_VERIFICACAO_MINUTOS = 30           # de quanto em quanto tempo o bot checa expiração

LOG_CHANNEL_ID = 1521897698419019907         # canal onde o bot manda o log de tudo que faz aqui

DATA_FILE = "data/quarentena.json"

MENSAGEM_QUARENTENA = (
    "Olá! Você entrou em quarentena por inatividade.\n\n"
    "Durante nosso período de avaliação, não identificamos atividade suficiente da sua "
    "parte. Para manter o clube ativo, jogadores inativos passam por esta etapa antes de "
    "uma remoção definitiva.\n\n"
    "Caso deseje continuar fazendo parte da **TryHarders RL**, basta responder neste canal "
    "dentro de **7 dias**.\n\n"
    "Se não houver nenhuma resposta nesse período, você será removido automaticamente do clube."
)

MENSAGEM_REMOCAO_FINAL = (
    "Olá! Você foi removido da **TryHarders RL** porque não houve nenhuma interação "
    "durante o período de quarentena de 7 dias.\n\n"
    "Caso queira receber uma nova oportunidade para voltar ao clube, entre em contato com "
    "**ravokes** pelo Discord. Após a análise da Staff, você poderá receber uma nova chance "
    "para demonstrar sua atividade."
)


# ── Helpers de leitura/escrita ──────────────────────────────────────────────
def ler_dados() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"ativos": {}}


def salvar_dados(dados: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


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
    @commands.bot_has_permissions(kick_members=True, manage_roles=True, manage_channels=True)
    async def demotar(self, ctx: commands.Context, membro: discord.Member = None, *, motivo: str = None):
        """Coloca um jogador em quarentena por inatividade.

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
            await ctx.send("❌ Não é possível colocar um bot em quarentena.", delete_after=6)
            return

        if membro.guild_permissions.administrator:
            await ctx.send("❌ Não é possível colocar um administrador em quarentena.", delete_after=6)
            return

        if membro.top_role >= ctx.guild.me.top_role:
            await ctx.send(
                "❌ Não consigo gerenciar esse membro — o cargo dele é igual ou "
                "maior que o meu cargo mais alto.",
                delete_after=8
            )
            return

        dados = ler_dados()
        if str(membro.id) in dados["ativos"]:
            canal_existente = self.bot.get_channel(dados["ativos"][str(membro.id)]["channel_id"])
            mencao = canal_existente.mention if canal_existente else "canal antigo (não encontrado)"
            await ctx.send(f"⚠️ **{membro}** já está em quarentena. Veja {mencao}.", delete_after=8)
            return

        guild = ctx.guild

        # 1) Salva e remove TODOS os cargos atuais do membro (exceto @everyone e
        #    cargos "managed", que pertencem a integrações/bots e não podem ser removidos manualmente)
        cargos_atuais = [r for r in membro.roles if r != guild.default_role and not r.managed]
        cargos_removidos_ids = [r.id for r in cargos_atuais]

        if cargos_atuais:
            try:
                await membro.remove_roles(*cargos_atuais, reason="Marcado para quarentena por inatividade")
            except discord.Forbidden:
                await ctx.send("⚠️ Não consegui remover todos os cargos (permissão insuficiente).")

        # 2) Adiciona o cargo Quarentena
        cargo_quarentena = await self.obter_cargo_quarentena(guild)
        try:
            await membro.add_roles(cargo_quarentena, reason="Quarentena por inatividade")
        except discord.Forbidden:
            await ctx.send("❌ Não tenho permissão para atribuir o cargo Quarentena.", delete_after=8)
            return

        # 3) Cria o canal privado de quarentena
        categoria = discord.utils.get(guild.categories, name=QUARENTENA_CATEGORY_NAME)
        if categoria is None:
            categoria = await guild.create_category(QUARENTENA_CATEGORY_NAME)

        nome_canal = f"quarentena-{membro.name}".lower().replace(" ", "-")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
            ),
            membro: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        for staff_id in STAFF_ROLE_IDS:
            staff_role = guild.get_role(staff_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            reason=f"Quarentena de {membro} — ação de {ctx.author}",
        )

        # 4) Envia a mensagem de aviso no canal (em vez de DM)
        await canal.send(f"{membro.mention}")
        await canal.send(MENSAGEM_QUARENTENA)

        # 5) Inicia o contador de 7 dias
        agora = datetime.now(timezone.utc)
        expira_em = agora + timedelta(days=DIAS_QUARENTENA)

        dados["ativos"][str(membro.id)] = {
            "guild_id": guild.id,
            "channel_id": canal.id,
            "user_name": str(membro),
            "motivo": motivo or "Inatividade",
            "iniciado_em": agora.isoformat(),
            "expira_em": expira_em.isoformat(),
            "respondido": False,
            "cargos_removidos": cargos_removidos_ids,
        }
        salvar_dados(dados)

        confirmacao = discord.Embed(
            title="🔒 Jogador colocado em quarentena",
            description=f"**{membro}** foi movido para quarentena em {canal.mention}.",
            color=0xFEE75C,
        )
        confirmacao.add_field(name="Prazo", value=f"{DIAS_QUARENTENA} dias (expira {discord.utils.format_dt(expira_em, style='F')})", inline=False)
        await ctx.send(embed=confirmacao)
        print(f"[DEMOTE] 🔒 {membro} entrou em quarentena por {ctx.author}. Expira em {expira_em.isoformat()}.")

        nomes_cargos = ", ".join(r.name for r in cargos_atuais) if cargos_atuais else "Nenhum cargo (o membro não tinha cargos)"
        await self.enviar_log(
            title="🔒 Membro colocado em quarentena",
            description=f"{membro.mention} (`{membro}` / `{membro.id}`) foi colocado em quarentena por {ctx.author.mention}.",
            color=0xFEE75C,
            fields=[
                ("Motivo", motivo or "Inatividade"),
                ("Canal criado", canal.mention),
                ("Cargos removidos e salvos", nomes_cargos),
                ("Expira em", discord.utils.format_dt(expira_em, style='F')),
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
                    "**TryHarders RL**. Bem-vindo(a) de volta à atividade!"
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
                "**TryHarders RL**. Bem-vindo(a) de volta à atividade!"
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
                    embed.set_footer(text="TryHarders RL")
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

        if alterou:
            salvar_dados(dados)

    @checar_expiracoes.before_loop
    async def antes_de_checar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Demote(bot))
