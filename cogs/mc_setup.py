"""!setupmine — cria os cargos e canais do servidor de Minecraft Survival.

Pode rodar de novo sem medo: o que já existe é reaproveitado (não duplica),
e as permissões dos canais são reaplicadas.

Acesso: @everyone NÃO vê nada (só o canal da whitelist de quem entra). Ao ser
aprovado na whitelist a pessoa recebe o cargo 🌱・Novato e passa a ver o servidor.
"""
import discord
from discord.ext import commands

from cogs import mc_config as cfg

SEP_LINHA = "━" * 20

P_NENHUMA = discord.Permissions.none()
P_ADMIN = discord.Permissions(administrator=True)
P_GESTOR = discord.Permissions(
    manage_channels=True, manage_messages=True, manage_nicknames=True, kick_members=True,
    ban_members=True, moderate_members=True, view_audit_log=True, mention_everyone=True,
)
P_MOD = discord.Permissions(
    manage_messages=True, manage_nicknames=True, kick_members=True, moderate_members=True,
)
P_AJUDANTE = discord.Permissions(manage_messages=True, moderate_members=True)

# (chave, nome, cor, permissões, hoist) — na ordem de cima pra baixo na hierarquia.
# cor None = cargo "título/separador" (fica sem cor)
CARGOS = [
    ("dir_h",         "👑・𝗗𝗜𝗥𝗘𝗖̧𝗔̃𝗢",             None,     P_NENHUMA,  False),
    ("fundador",      "👑・Fundador",               0xF1C40F, P_ADMIN,    True),
    ("diretor",       "💠・Diretor da Tryharders",  0x3498DB, P_ADMIN,    True),
    ("adm_try",       "⚜️・Adm da Tryharders",      0x9B59B6, P_ADMIN,    True),
    ("adm_surv",      "⛏️・Adm do Survival",        0xE67E22, P_GESTOR,   True),
    ("sep1",          SEP_LINHA,                    None,     P_NENHUMA,  False),
    ("eq_h",          "🛡️・𝗘𝗤𝗨𝗜𝗣𝗘",                None,     P_NENHUMA,  False),
    ("administrador", "🔨・Administrador",          0xE74C3C, P_GESTOR,   True),
    ("moderador",     "🛡️・Moderador",              0x2ECC71, P_MOD,      True),
    ("ajudante",      "🔧・Ajudante",               0x1ABC9C, P_AJUDANTE, True),
    ("sep2",          SEP_LINHA,                    None,     P_NENHUMA,  False),
    ("surv_h",        "🌲・𝗦𝗨𝗥𝗩𝗜𝗩𝗔𝗟",              None,     P_NENHUMA,  False),
    ("vip",           "💎・VIP",                    0x00E5FF, P_NENHUMA,  True),
    ("veterano",      "🏆・Veterano",               0xF39C12, P_NENHUMA,  True),
    ("sobrevivente",  "⛏️・Sobrevivente",           0x95A5A6, P_NENHUMA,  True),
    ("novato",        "🌱・Novato",                 0x7BED9F, P_NENHUMA,  False),
    ("sem_wl",        "🔒・Sem Whitelist",          0x992D22, P_NENHUMA,  False),
    ("sep3",          SEP_LINHA,                    None,     P_NENHUMA,  False),
    ("extras_h",      "🎮・𝗘𝗫𝗧𝗥𝗔𝗦",                None,     P_NENHUMA,  False),
    ("criador",       "🎥・Criador de Conteúdo",    0xFF69B4, P_NENHUMA,  False),
    ("bots",          "🤖・Bots",                   0x7289DA, P_NENHUMA,  False),
]

SEPARADORES = {"dir_h", "sep1", "eq_h", "sep2", "surv_h", "sep3", "extras_h"}

# Cargo de quem ainda não fez a whitelist: NÃO enxerga canal nenhum do servidor
CARGO_SEM_WL = "sem_wl"

# Quem aprova whitelists (e pode escrever nos canais só-leitura)
STAFF = ["fundador", "diretor", "adm_try", "adm_surv", "administrador", "moderador", "ajudante"]
# Quem enxerga o servidor
ACESSO = [c[0] for c in CARGOS if c[0] not in SEPARADORES and c[0] != CARGO_SEM_WL]
# Quem pode escrever nos canais só-leitura (anúncios, regras...)
PODE_ESCREVER_EM_LEITURA = set(STAFF) | {"bots"}
# Cargo que recebe um ping quando chega uma whitelist nova
CARGO_PING = "moderador"
# Cargo dado ao ser aprovado na whitelist
CARGO_MEMBRO = "novato"

# (nome da categoria, tipo, canais) — "ro" = só leitura, "rw" = todos escrevem
ESTRUTURA = [
    ("📌 INFORMAÇÕES", "texto", [
        ("📢│anúncios", "ro"),
        ("📖│regras", "ro"),
        ("📋│informações", "ro"),
        ("🔗│ip-do-servidor", "ro"),
    ]),
    ("💬 COMUNIDADE", "texto", [
        ("💬│chat-geral", "rw"),
        ("📸│prints-e-clipes", "rw"),
        ("😂│memes", "rw"),
        ("🤝│procurar-equipe", "rw"),
        ("❓│dúvidas", "rw"),
    ]),
    ("⛏️ MINECRAFT", "texto", [
        ("🌍│mundo-survival", "rw"),
        ("🏡│construções", "rw"),
        ("⚔️│pvp", "rw"),
        ("💰│trocas-e-vendas", "rw"),
        ("📦│itens-e-conquistas", "rw"),
        ("🗺️│exploração", "rw"),
    ]),
    ("🔊 CANAIS DE VOZ", "voz", [
        ("🔊 Geral", "rw"),
        ("⛏️ Mineração", "rw"),
        ("🏡 Construindo", "rw"),
        ("⚔️ Aventura", "rw"),
        ("💤 AFK", "rw"),
    ]),
]


def _overwrites(guild: discord.Guild, roles: dict[str, discord.Role], tipo: str, modo: str):
    ow = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    for chave in ACESSO:
        role = roles.get(chave)
        if role is None:
            continue
        if tipo == "voz":
            ow[role] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
        elif modo == "ro" and chave not in PODE_ESCREVER_EM_LEITURA:
            ow[role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=False, add_reactions=True,
            )
        else:
            ow[role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=True,
            )
    # quem está sem whitelist não vê nada: é obrigado a fazer a whitelist
    sem_wl = roles.get(CARGO_SEM_WL)
    if sem_wl is not None:
        ow[sem_wl] = discord.PermissionOverwrite(
            view_channel=False, send_messages=False, connect=False, read_message_history=False,
        )
    # o próprio bot sempre enxerga tudo
    ow[guild.me] = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, manage_channels=True, connect=True,
    )
    return ow


class McSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _garantir_cargos(self, guild: discord.Guild, conf: dict) -> tuple[dict, int, int]:
        ids_salvos = conf.setdefault("roles", {})
        roles: dict[str, discord.Role] = {}
        criados = reaproveitados = 0

        for chave, nome, cor, perms, hoist in CARGOS:
            role = guild.get_role(int(ids_salvos.get(chave, 0)))
            if role is None and chave not in ("sep1", "sep2", "sep3"):  # os separadores têm nome repetido
                role = discord.utils.get(guild.roles, name=nome)
            if role is not None:
                reaproveitados += 1
            else:
                role = await guild.create_role(
                    name=nome,
                    colour=discord.Colour(cor) if cor else discord.Colour.default(),
                    permissions=perms,
                    hoist=hoist,
                    mentionable=False,
                    reason="!setupmine",
                )
                criados += 1
            roles[chave] = role
            ids_salvos[chave] = role.id
        return roles, criados, reaproveitados

    async def _ordenar_cargos(self, guild: discord.Guild, roles: dict[str, discord.Role]) -> bool:
        """Coloca os cargos na ordem da lista, logo abaixo do cargo do bot."""
        topo = guild.me.top_role.position
        posicoes = {}
        for i, (chave, *_rest) in enumerate(CARGOS):
            pos = topo - 1 - i
            if pos < 1:
                return False
            posicoes[roles[chave]] = pos
        try:
            await guild.edit_role_positions(positions=posicoes, reason="!setupmine — ordem da hierarquia")
            return True
        except discord.HTTPException:
            return False

    async def _garantir_canais(self, guild: discord.Guild, roles: dict) -> tuple[int, int]:
        criados = existentes = 0
        for nome_cat, tipo, canais in ESTRUTURA:
            cat_ow = _overwrites(guild, roles, tipo, "rw")
            categoria = discord.utils.get(guild.categories, name=nome_cat)
            if categoria is None:
                categoria = await guild.create_category(nome_cat, overwrites=cat_ow, reason="!setupmine")
            else:
                await categoria.edit(overwrites=cat_ow, reason="!setupmine")

            for nome, modo in canais:
                ow = _overwrites(guild, roles, tipo, modo)
                lista = categoria.voice_channels if tipo == "voz" else categoria.text_channels
                canal = discord.utils.get(lista, name=nome if tipo == "voz" else nome.lower())
                if canal is not None:
                    await canal.edit(overwrites=ow, reason="!setupmine")
                    existentes += 1
                    continue
                if tipo == "voz":
                    await guild.create_voice_channel(nome, category=categoria, overwrites=ow, reason="!setupmine")
                else:
                    await guild.create_text_channel(nome, category=categoria, overwrites=ow, reason="!setupmine")
                criados += 1
        return criados, existentes

    @commands.command(name="setupmine")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setupmine(self, ctx: commands.Context):
        """!setupmine — cria cargos e canais do servidor de Minecraft."""
        guild = ctx.guild
        perms = guild.me.guild_permissions
        if not (perms.administrator or (perms.manage_channels and perms.manage_roles)):
            await ctx.send("⛔ Preciso das permissões **Gerenciar Canais** e **Gerenciar Cargos**.", delete_after=15)
            return

        aviso = await ctx.send("⏳ Montando o servidor... isso leva alguns segundos.")
        try:
            conf = cfg.carregar()
            roles, r_novos, r_exist = await self._garantir_cargos(guild, conf)
            ordenou = await self._ordenar_cargos(guild, roles)
            c_novos, c_exist = await self._garantir_canais(guild, roles)

            # liga a whitelist nos cargos criados
            conf["staff_role_ids"] = [roles[k].id for k in STAFF]
            conf["ping_role_id"] = roles[CARGO_PING].id
            conf["member_role_id"] = roles[CARGO_MEMBRO].id
            conf["no_access_role_id"] = roles[CARGO_SEM_WL].id
            cfg.salvar(conf)
        except discord.Forbidden:
            await aviso.edit(content="⛔ Sem permissão pra criar isso. Confira as permissões do bot e tente de novo.")
            return
        except discord.HTTPException as e:
            await aviso.edit(content=f"⚠️ O Discord recusou uma das etapas: `{e}`\nRode `!setupmine` de novo pra continuar.")
            return

        linhas = [
            "✅ **Servidor montado!**",
            f"• Cargos: **{r_novos}** criados, {r_exist} já existiam",
            f"• Canais: **{c_novos}** criados, {c_exist} já existiam",
            "• Whitelist ligada: quem entra ganha **🔒・Sem Whitelist** (não vê nada) e, ao ser aprovado, "
            "troca por **🌱・Novato**. A equipe (Ajudante pra cima) aprova.",
        ]
        if not ordenou:
            linhas.append(
                "⚠️ Não consegui ordenar os cargos. Arraste o cargo do **bot** pro topo da lista de "
                "cargos e rode `!setupmine` de novo."
            )
        await aviso.edit(content="\n".join(linhas))


async def setup(bot: commands.Bot):
    await bot.add_cog(McSetup(bot))
