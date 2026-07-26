import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone

from cogs.players import CARGOS
from cogs.json_store import ler_json, salvar_json

# ─────────────────────────────────────────────
#  Cog: Treinos
#  Arquivo: cogs/treino.py
#
#  Espelha exatamente o cogs/campeonato.py — mesmo estilo, mesmas
#  funções, só trocando "campeonato/torneio" por "treino" pra não
#  bater nome de comando com o sistema de campeonatos.
#
#  /criar-treino e /treinar são slash commands.
#  !destreinar continua sendo comando de prefixo (!).
#
#  Cada treino gera DUAS mensagens no canal:
#    1) A mensagem de informações + botão "Entrar no Treino"
#    2) A mensagem com a lista de inscritos (atualizada à parte)
# ─────────────────────────────────────────────

DATA_FILE = "data/treinos.json"

RANKS_VALIDOS = {c["nome"].lower(): c for c in CARGOS if c["secao"] == "rank"}
RANK_TODOS = "Todos"

RANK_CHOICES = [app_commands.Choice(name=c["nome"], value=c["nome"]) for c in CARGOS if c["secao"] == "rank"]
RANK_CHOICES.append(app_commands.Choice(name="Todos os ranks", value=RANK_TODOS))

FORMATO_CHOICES = [
    app_commands.Choice(name="1v1", value="1v1"),
    app_commands.Choice(name="2v2", value="2v2"),
    app_commands.Choice(name="3v3", value="3v3"),
]

TIPO_CHOICES = [
    app_commands.Choice(name="Interno", value="Interno"),
    app_commands.Choice(name="Externo", value="Externo"),
]


def ler_treinos() -> dict:
    return ler_json(DATA_FILE, {})


def salvar_treinos(dados: dict):
    salvar_json(DATA_FILE, dados)


def _chave(nome: str) -> str:
    return nome.strip().lower()


def _membro_tem_rank(membro: discord.Member, rank_nome: str) -> bool:
    if rank_nome == RANK_TODOS:
        return True
    info = RANKS_VALIDOS.get(rank_nome.lower())
    if info is None:
        return True  # rank desconhecido — não bloqueia, deixa passar
    return any(r.id == info["id"] for r in membro.roles)


def _rank_display(rank_nome: str) -> str:
    if rank_nome == RANK_TODOS:
        return "Todos os ranks"
    info = RANKS_VALIDOS.get(rank_nome.lower())
    return f"{info['emoji']} {info['nome']}" if info else rank_nome


def construir_embed_info(info: dict) -> discord.Embed:
    """Mensagem 1: informações do treino (não muda depois de criada)."""
    embed = discord.Embed(title=f"🏋️ Treino: {info['nome']}", color=0x1FA2FF)
    embed.add_field(name="🎮 Rank exigido", value=_rank_display(info["rank"]), inline=True)
    embed.add_field(name="⚔️ Formato", value=info["formato"], inline=True)
    embed.add_field(name="🌍 Tipo", value=info["tipo"], inline=True)
    embed.add_field(name="🧑‍💼 Organizador", value=info["organizador"], inline=False)
    embed.set_footer(text="Clique no botão abaixo pra se inscrever!")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def construir_embed_resposta(info: dict, canal: discord.abc.GuildChannel) -> discord.Embed:
    """Embed enviada como resposta (reply) a uma mensagem, quando `link_mensagem` é informado —
    mesma ideia usada em /resultado (cogs/resultados.py)."""
    embed = discord.Embed(
        title=f"🏋️ Novo treino: {info['nome']}",
        description=f"As inscrições já estão abertas em {canal.mention}!",
        color=0x1FA2FF,
    )
    embed.add_field(name="🎮 Rank exigido", value=_rank_display(info["rank"]), inline=True)
    embed.add_field(name="⚔️ Formato", value=info["formato"], inline=True)
    embed.add_field(name="🌍 Tipo", value=info["tipo"], inline=True)
    embed.set_footer(text=f"Organizado por {info['organizador']}")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def construir_embed_lista(info: dict) -> discord.Embed:
    """Mensagem 2: lista de inscritos (atualizada toda vez que alguém entra/sai)."""
    inscritos = info.get("inscritos", {})
    embed = discord.Embed(
        title=f"📋 Lista de inscritos — {info['nome']}",
        description="\n".join(f"▸ <@{uid}>" for uid in inscritos.keys()) if inscritos else "*— ninguém inscrito ainda —*",
        color=0x1FA2FF,
    )
    embed.set_footer(text=f"{len(inscritos)} inscrito(s)")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


async def _dar_cargo(bot: commands.Bot, info: dict, membro_id: int):
    """Dá o cargo exclusivo do treino pra alguém, se ele ainda não tiver."""
    guild = bot.get_guild(info.get("guild_id"))
    role_id = info.get("role_id")
    if guild is None or role_id is None:
        return
    role = guild.get_role(role_id)
    membro = guild.get_member(membro_id)
    if role is None or membro is None:
        return
    if role not in membro.roles:
        try:
            await membro.add_roles(role, reason="Inscrito no treino")
        except discord.Forbidden:
            print(f"[TREINO] ⚠️ Sem permissão pra dar o cargo do treino '{info['nome']}' em {membro}.")


async def _remover_cargo(bot: commands.Bot, info: dict, membro_id: int):
    """Tira o cargo exclusivo do treino de alguém, se ele tiver."""
    guild = bot.get_guild(info.get("guild_id"))
    role_id = info.get("role_id")
    if guild is None or role_id is None:
        return
    role = guild.get_role(role_id)
    membro = guild.get_member(membro_id)
    if role is None or membro is None:
        return
    if role in membro.roles:
        try:
            await membro.remove_roles(role, reason="Saiu do treino")
        except discord.Forbidden:
            print(f"[TREINO] ⚠️ Sem permissão pra tirar o cargo do treino '{info['nome']}' de {membro}.")


async def _apagar_cargo(bot: commands.Bot, info: dict):
    """Apaga o cargo do treino inteiro (usado quando o treino acaba/é apagado)."""
    guild = bot.get_guild(info.get("guild_id"))
    role_id = info.get("role_id")
    if guild is None or role_id is None:
        return
    role = guild.get_role(role_id)
    if role is not None:
        try:
            await role.delete(reason=f"Treino '{info['nome']}' encerrado")
        except discord.Forbidden:
            print(f"[TREINO] ⚠️ Sem permissão pra apagar o cargo do treino '{info['nome']}'.")


async def _atualizar_lista(bot: commands.Bot, chave: str):
    dados = ler_treinos()
    info = dados.get(chave)
    if info is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is None:
        return
    try:
        msg = await canal.fetch_message(info["lista_message_id"])
        await msg.edit(embed=construir_embed_lista(info))
    except discord.NotFound:
        pass


# ── Modal que pergunta o país da pessoa ──────────────────────────────────────
class PaisModalTreino(discord.ui.Modal, title="Inscrição no Treino"):
    pais = discord.ui.TextInput(label="Qual o seu país?", placeholder="Ex: Brasil", max_length=50)

    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__()
        self.chave = chave
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        dados = ler_treinos()
        info = dados.get(self.chave)
        if info is None:
            await interaction.response.send_message("❌ Esse treino não existe mais.", ephemeral=True)
            return
        if str(interaction.user.id) in info["inscritos"]:
            await interaction.response.send_message("⚠️ Você já está inscrito nesse treino.", ephemeral=True)
            return

        info["inscritos"][str(interaction.user.id)] = {"pais": str(self.pais)}
        salvar_treinos(dados)
        await _atualizar_lista(self.bot, self.chave)
        await _dar_cargo(self.bot, info, interaction.user.id)
        await interaction.response.send_message(
            f"✅ Inscrição confirmada no treino **{info['nome']}**!", ephemeral=True
        )


# ── View de confirmação quando o rank não bate ───────────────────────────────
class ConfirmarRankViewTreino(discord.ui.View):
    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__(timeout=60)
        self.chave = chave
        self.bot = bot

    @discord.ui.button(label="Sim, quero mesmo assim", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PaisModalTreino(self.chave, self.bot))

    @discord.ui.button(label="Não, cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Inscrição cancelada.", view=None)


# ── View fixa no anúncio do treino (persistente, sobrevive a restart) ───────
class EntrarTreinoView(discord.ui.View):
    def __init__(self, chave: str, fechado: bool = False):
        super().__init__(timeout=None)
        self.chave = chave
        self.entrar.custom_id = f"treino_entrar:{chave}"
        if fechado:
            self.entrar.label = "🔒 Inscrições fechadas"
            self.entrar.style = discord.ButtonStyle.secondary
            self.entrar.disabled = True

    @discord.ui.button(label="🏋️ Entrar no Treino", style=discord.ButtonStyle.primary)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        dados = ler_treinos()
        info = dados.get(self.chave)
        if info is None:
            await interaction.response.send_message("❌ Esse treino não existe mais.", ephemeral=True)
            return
        if not info.get("inscricoes_abertas", True):
            await interaction.response.send_message("🔒 As inscrições desse treino estão fechadas no momento.", ephemeral=True)
            return
        if str(interaction.user.id) in info["inscritos"]:
            await interaction.response.send_message("⚠️ Você já está inscrito nesse treino.", ephemeral=True)
            return

        membro = interaction.user
        if isinstance(membro, discord.Member) and _membro_tem_rank(membro, info["rank"]):
            await interaction.response.send_modal(PaisModalTreino(self.chave, bot))
        else:
            await interaction.response.send_message(
                f"⚠️ Esse treino pede o rank **{info['rank']}**, e você não tem esse cargo. "
                f"Deseja se inscrever mesmo assim?",
                view=ConfirmarRankViewTreino(self.chave, bot),
                ephemeral=True,
            )


async def _atualizar_botao_inscricao(bot: commands.Bot, chave: str, fechado: bool):
    """Reedita a mensagem de anúncio pra trocar o botão de Entrar no Treino
    pro estado de aberto/fechado (mantém tudo mais igual)."""
    dados = ler_treinos()
    info = dados.get(chave)
    if info is None or info.get("canal_id") is None or info.get("message_id") is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is None:
        return
    try:
        msg = await canal.fetch_message(info["message_id"])
        await msg.edit(view=EntrarTreinoView(chave, fechado=fechado))
    except discord.NotFound:
        pass


async def _apagar_treino(bot: commands.Bot, chave: str):
    dados = ler_treinos()
    info = dados.get(chave)
    if info is None:
        return
    canal = bot.get_channel(info["canal_id"])
    if canal is not None:
        for msg_id in (info.get("message_id"), info.get("lista_message_id")):
            if msg_id is None:
                continue
            try:
                msg = await canal.fetch_message(msg_id)
                await msg.delete()
            except discord.NotFound:
                pass
    await _apagar_cargo(bot, info)
    del dados[chave]
    salvar_treinos(dados)


class ConfirmarExclusaoViewTreino(discord.ui.View):
    def __init__(self, chave: str, bot: commands.Bot):
        super().__init__(timeout=30)
        self.chave = chave
        self.bot = bot

    @discord.ui.button(label="Sim, apagar", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _apagar_treino(self.bot, self.chave)
        await interaction.response.edit_message(content="🗑️ Treino apagado.", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelado, o treino continua ativo.", view=None)


async def _autocomplete_treino(interaction: discord.Interaction, current: str):
    dados = ler_treinos()
    return [
        app_commands.Choice(name=info["nome"], value=info["nome"])
        for info in dados.values()
        if current.lower() in info["nome"].lower()
    ][:25]


class Treino(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificar_cargos_treino.start()

    def cog_unload(self):
        self.verificar_cargos_treino.cancel()

    # ── A cada 10 min, confere se todo mundo inscrito ainda tem o cargo do
    # treino dele — se por algum motivo sumiu (ex: alguém removeu na mão,
    # bot caiu no meio da inscrição), devolve o cargo automaticamente.
    @tasks.loop(minutes=10)
    async def verificar_cargos_treino(self):
        dados = ler_treinos()
        for info in dados.values():
            if info.get("role_id") is None or info.get("guild_id") is None:
                continue
            for uid_str in info.get("inscritos", {}).keys():
                try:
                    await _dar_cargo(self.bot, info, int(uid_str))
                except Exception as e:
                    # Um inscrito problemático (ex: saiu do servidor, cargo
                    # deletado) não pode travar a checagem dos demais.
                    print(f"[TREINO] ⚠️ Erro ao verificar cargo de {uid_str}: {e}")

    @verificar_cargos_treino.before_loop
    async def antes_verificar_cargos_treino(self):
        await self.bot.wait_until_ready()

    # ── /treino ──────────────────────────────────────────────────────────────
    @app_commands.command(name="treino", description="Cria o anúncio de um treino com botão de inscrição.")
    @app_commands.describe(
        nome="Nome do treino",
        rank="Rank exigido pra participar (ou 'Todos os ranks')",
        formato="Formato das partidas",
        tipo="O treino é interno ou externo?",
        organizador="Quem está organizando",
        link_mensagem="(Opcional) Link de uma mensagem pra responder anunciando o treino",
    )
    @app_commands.choices(rank=RANK_CHOICES, formato=FORMATO_CHOICES, tipo=TIPO_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def treino(
        self,
        interaction: discord.Interaction,
        nome: str,
        rank: app_commands.Choice[str],
        formato: app_commands.Choice[str],
        tipo: app_commands.Choice[str],
        organizador: str,
        link_mensagem: str = None,
    ):
        chave = _chave(nome)
        dados = ler_treinos()
        if chave in dados:
            await interaction.response.send_message(
                f"❌ Já existe um treino chamado **{nome}**. Escolha outro nome.", ephemeral=True
            )
            return

        info = {
            "nome": nome,
            "rank": rank.value,
            "formato": formato.value,
            "tipo": tipo.value,
            "organizador": organizador,
            "canal_id": interaction.channel_id,
            "guild_id": interaction.guild_id,
            "message_id": None,
            "lista_message_id": None,
            "role_id": None,
            "inscritos": {},
            "inscricoes_abertas": True,
        }

        # Cargo exclusivo do treino: só enfeite, sem permissão nenhuma,
        # pra facilitar marcar todo mundo inscrito de uma vez depois
        try:
            role = await interaction.guild.create_role(
                name=f"🏋️ {nome}",
                permissions=discord.Permissions.none(),
                mentionable=True,
                reason=f"Cargo do treino '{nome}'",
            )
            info["role_id"] = role.id
        except discord.Forbidden:
            print(f"[TREINO] ⚠️ Sem permissão pra criar o cargo do treino '{nome}'.")

        # Responde só pra você, de forma discreta — o anúncio de verdade vai
        # como mensagem própria do bot, sem aparecer como resposta ao seu comando
        await interaction.response.send_message("✅ Treino criado!", ephemeral=True)

        canal = interaction.channel
        msg_info = await canal.send(embed=construir_embed_info(info), view=EntrarTreinoView(chave))
        msg_lista = await canal.send(embed=construir_embed_lista(info))

        info["message_id"] = msg_info.id
        info["lista_message_id"] = msg_lista.id
        dados[chave] = info
        salvar_treinos(dados)

        # ── Responde a mensagem informada (opcional), igual ao /resultado ──────
        if link_mensagem:
            msg_alvo = None
            # Extrai IDs do link: .../channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
            try:
                partes = link_mensagem.strip().split("/")
                msg_id = int(partes[-1])
                ch_id  = int(partes[-2])
                canal_link = self.bot.get_channel(ch_id)
                if canal_link:
                    msg_alvo = await canal_link.fetch_message(msg_id)
            except Exception as e:
                print(f"[TREINO] ⚠️ Não foi possível buscar a mensagem pelo link: {e}")

            embed_resp = construir_embed_resposta(info, canal)
            if msg_alvo:
                await msg_alvo.reply(embed=embed_resp)
            else:
                await canal.send(embed=embed_resp)

    @treino.error
    async def treino_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem criar treinos.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro ao criar treino: {error}", ephemeral=True)

    # ── /treinar ─────────────────────────────────────────────────────────────
    @app_commands.command(name="treinar", description="Inscreve uma ou mais pessoas manualmente num treino (sem checar rank).")
    @app_commands.describe(
        treino="Nome do treino",
        membro1="Quem vai ser inscrito",
        membro2="(opcional) mais alguém",
        membro3="(opcional) mais alguém",
        membro4="(opcional) mais alguém",
        membro5="(opcional) mais alguém",
    )
    @app_commands.autocomplete(treino=_autocomplete_treino)
    @app_commands.checks.has_permissions(administrator=True)
    async def treinar(
        self,
        interaction: discord.Interaction,
        treino: str,
        membro1: discord.Member,
        membro2: discord.Member = None,
        membro3: discord.Member = None,
        membro4: discord.Member = None,
        membro5: discord.Member = None,
    ):
        chave = _chave(treino)
        dados = ler_treinos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum treino chamado **{treino}**.", ephemeral=True)
            return

        membros = [m for m in (membro1, membro2, membro3, membro4, membro5) if m is not None]

        inscritos_agora = []
        ja_estavam = []
        ids_novos = []
        for membro in membros:
            if str(membro.id) in info["inscritos"]:
                ja_estavam.append(membro.display_name)
            else:
                info["inscritos"][str(membro.id)] = {"pais": "—"}
                inscritos_agora.append(membro.display_name)
                ids_novos.append(membro.id)

        salvar_treinos(dados)
        await _atualizar_lista(self.bot, chave)
        for membro_id in ids_novos:
            await _dar_cargo(self.bot, info, membro_id)

        partes = []
        if inscritos_agora:
            partes.append(f"✅ Inscrito(s) em **{info['nome']}**: {', '.join(inscritos_agora)}")
        if ja_estavam:
            partes.append(f"⚠️ Já estavam inscritos (ignorados): {', '.join(ja_estavam)}")

        await interaction.response.send_message("\n".join(partes) or "⚠️ Nada pra fazer.", ephemeral=True)

    @treinar.error
    async def treinar_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── /deletar-treino ──────────────────────────────────────────────────────
    @app_commands.command(name="deletar-treino", description="Apaga um treino (as duas mensagens e todos os inscritos).")
    @app_commands.describe(treino="Qual treino apagar")
    @app_commands.autocomplete(treino=_autocomplete_treino)
    @app_commands.checks.has_permissions(administrator=True)
    async def deletar_treino(self, interaction: discord.Interaction, treino: str):
        chave = _chave(treino)
        dados = ler_treinos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum treino chamado **{treino}**.", ephemeral=True)
            return

        view = ConfirmarExclusaoViewTreino(chave, self.bot)
        await interaction.response.send_message(
            f"⚠️ Tem certeza que quer apagar o treino **{info['nome']}**? "
            f"Isso vai apagar as mensagens e **{len(info['inscritos'])} inscrição(ões)**, sem volta.",
            view=view,
            ephemeral=True,
        )

    @deletar_treino.error
    async def deletar_treino_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── /fechar-inscricoes-treino ────────────────────────────────────────────
    @app_commands.command(name="fechar-inscricoes-treino", description="Fecha as inscrições de um treino (o botão fica travado).")
    @app_commands.describe(treino="Qual treino fechar")
    @app_commands.autocomplete(treino=_autocomplete_treino)
    @app_commands.checks.has_permissions(administrator=True)
    async def fechar_inscricoes_treino(self, interaction: discord.Interaction, treino: str):
        chave = _chave(treino)
        dados = ler_treinos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum treino chamado **{treino}**.", ephemeral=True)
            return

        if not info.get("inscricoes_abertas", True):
            await interaction.response.send_message(f"⚠️ As inscrições de **{info['nome']}** já estavam fechadas.", ephemeral=True)
            return

        info["inscricoes_abertas"] = False
        salvar_treinos(dados)
        await _atualizar_botao_inscricao(self.bot, chave, fechado=True)
        await interaction.response.send_message(f"🔒 Inscrições de **{info['nome']}** fechadas.", ephemeral=True)

    @fechar_inscricoes_treino.error
    async def fechar_inscricoes_treino_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── /abrir-inscricoes-treino ─────────────────────────────────────────────
    @app_commands.command(name="abrir-inscricoes-treino", description="Reabre as inscrições de um treino.")
    @app_commands.describe(treino="Qual treino reabrir")
    @app_commands.autocomplete(treino=_autocomplete_treino)
    @app_commands.checks.has_permissions(administrator=True)
    async def abrir_inscricoes_treino(self, interaction: discord.Interaction, treino: str):
        chave = _chave(treino)
        dados = ler_treinos()
        info = dados.get(chave)
        if info is None:
            await interaction.response.send_message(f"❌ Não encontrei nenhum treino chamado **{treino}**.", ephemeral=True)
            return

        if info.get("inscricoes_abertas", True):
            await interaction.response.send_message(f"⚠️ As inscrições de **{info['nome']}** já estavam abertas.", ephemeral=True)
            return

        info["inscricoes_abertas"] = True
        salvar_treinos(dados)
        await _atualizar_botao_inscricao(self.bot, chave, fechado=False)
        await interaction.response.send_message(f"✅ Inscrições de **{info['nome']}** reabertas.", ephemeral=True)

    @abrir_inscricoes_treino.error
    async def abrir_inscricoes_treino_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Só **Administradores** podem usar este comando.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Erro: {error}", ephemeral=True)

    # ── !destreinar <membro> <nome do treino> — tira alguém da lista ───────
    @commands.command(name="destreinar")
    @commands.has_permissions(administrator=True)
    async def destreinar(self, ctx: commands.Context, membro: discord.Member, *, nome_treino: str):
        """Tira alguém da lista de inscritos de um treino.

        Uso: !destreinar @pessoa <nome do treino>
        """
        chave = _chave(nome_treino)
        dados = ler_treinos()
        info = dados.get(chave)
        if info is None:
            await ctx.send(f"❌ Não encontrei nenhum treino chamado **{nome_treino}**.", delete_after=8)
            return

        if str(membro.id) not in info["inscritos"]:
            await ctx.send(f"⚠️ **{membro.display_name}** não está inscrito em **{info['nome']}**.", delete_after=6)
            return

        del info["inscritos"][str(membro.id)]
        salvar_treinos(dados)
        await _atualizar_lista(self.bot, chave)
        await _remover_cargo(self.bot, info, membro.id)

        await ctx.send(f"✅ **{membro.display_name}** foi removido de **{info['nome']}**.", delete_after=8)

    @destreinar.error
    async def destreinar_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Só **Administradores** podem usar este comando.", delete_after=6)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado. Marque a pessoa com `@` ou use o nick certinho.", delete_after=6)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Uso: `!destreinar @pessoa <nome do treino>`", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(Treino(bot))
