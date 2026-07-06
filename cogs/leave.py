import discord
from discord.ext import commands
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  Cog: Despedida (saída de membros)
#  Arquivo: cogs/leave.py
#  Evento: on_member_remove / on_member_ban
# ─────────────────────────────────────────────

LEAVE_CHANNEL_ID = 1522984476450361364

COR_DESPEDIDA = 0x992D22  # vermelho escuro — saída normal (a pessoa que decidiu ir embora)
COR_EXPULSO   = 0xE67E22  # laranja — expulso (kick)
COR_BANIDO    = 0x2C2F33  # quase preto — banido (a punição mais séria)

JANELA_AUDITORIA_SEGUNDOS = 15


async def _buscar_executor(guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
    """Procura no audit log quem fez a ação (kick) recentemente contra esse alvo.
    Retorna (executor, motivo) ou (None, None) se não achar nada recente."""
    try:
        async for entry in guild.audit_logs(limit=8, action=action):
            delta = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
            if delta > JANELA_AUDITORIA_SEGUNDOS:
                break
            if getattr(entry.target, "id", None) != target_id:
                continue
            return entry.user, entry.reason
    except discord.Forbidden:
        print("[LEAVE] ⚠️ Sem permissão pra ler o Audit Log (é necessário 'Ver Registro de Auditoria').")
    except discord.HTTPException:
        pass
    return None, None


def _tempo_no_servidor(entrou_em) -> str:
    if entrou_em is None:
        return "desconhecido"
    agora = datetime.now(timezone.utc)
    delta = agora - entrou_em
    dias = delta.days

    if dias >= 365:
        anos, resto = divmod(dias, 365)
        texto = f"{anos} ano(s)"
        if resto:
            texto += f" e {resto} dia(s)"
        return texto
    if dias >= 30:
        meses, resto = divmod(dias, 30)
        texto = f"{meses} mês(es)"
        if resto:
            texto += f" e {resto} dia(s)"
        return texto
    if dias >= 1:
        return f"{dias} dia(s)"

    horas = delta.seconds // 3600
    return f"{horas} hora(s)" if horas else "menos de 1 hora"


class Despedida(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild

        # Se foi banido, quem cuida da mensagem é o on_member_ban — evita duplicar
        try:
            await guild.fetch_ban(member)
            return
        except discord.NotFound:
            pass
        except discord.HTTPException:
            pass

        channel = self.bot.get_channel(LEAVE_CHANNEL_ID)
        if channel is None:
            print(f"[LEAVE] ⚠️  Canal {LEAVE_CHANNEL_ID} não encontrado.")
            return

        tempo = _tempo_no_servidor(member.joined_at)

        executor, motivo = await _buscar_executor(guild, discord.AuditLogAction.kick, member.id)

        if executor:
            embed = discord.Embed(
                title="👢 Membro expulso",
                description=f"**{member}** foi **expulso(a)** da **{guild.name}**.",
                color=COR_EXPULSO,
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="🛡️ Expulso por", value=executor.mention, inline=True)
            embed.add_field(name="📝 Motivo", value=motivo or "Nenhum motivo informado", inline=True)
            embed.add_field(name="⏳ Tempo no servidor", value=tempo, inline=True)
            embed.add_field(name="👥 Membros restantes", value=f"`{guild.member_count}`", inline=True)
            embed.set_footer(
                text=f"{guild.name}",
                icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
            )
            await channel.send(content=member.mention, embed=embed)
            print(f"[LEAVE] ✅ Mensagem de expulsão enviada para {member} no canal #{channel.name}.")
            return

        # Saída normal — a pessoa decidiu ir embora sozinha
        embed = discord.Embed(
            title="💔 Mais um saiu do clube...",
            description=f"**{member}** deixou a **{guild.name}**. Sentiremos falta! 🕊️",
            color=COR_DESPEDIDA,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="⏳ Tempo no servidor",  value=tempo, inline=True)
        embed.add_field(name="👥 Membros restantes",  value=f"`{guild.member_count}`", inline=True)
        embed.add_field(
            name="📅 Saiu em",
            value=discord.utils.format_dt(datetime.now(timezone.utc), style="f"),
            inline=True,
        )

        embed.set_footer(
            text=f"{guild.name}",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
        )

        # Menciona quem saiu fora do embed também
        await channel.send(content=member.mention, embed=embed)
        print(f"[LEAVE] ✅ Mensagem de saída enviada para {member} no canal #{channel.name}.")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel = self.bot.get_channel(LEAVE_CHANNEL_ID)
        if channel is None:
            print(f"[LEAVE] ⚠️  Canal {LEAVE_CHANNEL_ID} não encontrado.")
            return

        executor, motivo = await _buscar_executor(guild, discord.AuditLogAction.ban, user.id)

        embed = discord.Embed(
            title="🔨 Membro banido",
            description=f"**{user}** foi **banido(a)** da **{guild.name}**.",
            color=COR_BANIDO,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="🛡️ Banido por", value=executor.mention if executor else "Não identificado", inline=True)
        embed.add_field(name="📝 Motivo", value=motivo or "Nenhum motivo informado", inline=True)
        embed.add_field(name="👥 Membros restantes", value=f"`{guild.member_count}`", inline=True)
        embed.set_footer(
            text=f"{guild.name}",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
        )

        await channel.send(content=f"`{user}` (`{user.id}`)", embed=embed)
        print(f"[LEAVE] ✅ Mensagem de banimento enviada para {user} no canal #{channel.name}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Despedida(bot))
