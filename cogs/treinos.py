import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import re
from cogs.backup import ler, salvar, agora_str

# ─────────────────────────────────────────────
#  Cog: Agendamento de Treinos
#  Arquivo: cogs/treinos.py
#  /treino — agenda e lembra 30 min antes
# ─────────────────────────────────────────────

ADMIN_ROLE_ID = 1511894837790769204


def parse_data(data_str: str, hora_str: str) -> datetime | None:
    """
    Converte strings como '25/06' e '20:00' em datetime UTC-3 (Brasília).
    """
    try:
        ano  = datetime.now().year
        dt   = datetime.strptime(f"{data_str.strip()}/{ano} {hora_str.strip()}", "%d/%m/%Y %H:%M")
        # Brasília = UTC-3
        dt_utc = dt.replace(tzinfo=timezone(timedelta(hours=-3)))
        return dt_utc
    except Exception:
        return None


class Treinos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificar_treinos.start()

    def cog_unload(self):
        self.verificar_treinos.cancel()

    # ── /treino ───────────────────────────────────────────────────────────────
    @app_commands.command(name="treino", description="Agenda um treino e lembra o time 30 min antes.")
    @app_commands.checks.has_role(ADMIN_ROLE_ID)
    @app_commands.describe(
        data="Data do treino (ex: 25/06)",
        hora="Horário do treino (ex: 20:00)",
        descricao="O que será treinado (opcional)",
        canal="Canal onde o lembrete será enviado",
    )
    async def treino(
        self,
        interaction: discord.Interaction,
        data: str,
        hora: str,
        canal: discord.TextChannel,
        descricao: str = "Treino geral",
    ):
        dt = parse_data(data, hora)
        if dt is None:
            await interaction.response.send_message(
                "❌ Data ou hora inválida. Use o formato `DD/MM` e `HH:MM`.\nEx: `25/06` e `20:00`",
                ephemeral=True
            )
            return

        agora = datetime.now(timezone.utc)
        if dt <= agora:
            await interaction.response.send_message(
                "❌ A data/hora do treino já passou!", ephemeral=True
            )
            return

        treinos = ler("treinos")
        treino = {
            "id":        len(treinos) + 1,
            "data_str":  data,
            "hora_str":  hora,
            "timestamp": dt.isoformat(),
            "descricao": descricao,
            "canal_id":  canal.id,
            "lembrete_enviado": False,
            "criado_por": interaction.user.display_name,
        }
        treinos.append(treino)
        salvar("treinos", treinos)

        dt_discord = discord.utils.format_dt(dt, style="F")
        dt_relativo = discord.utils.format_dt(dt, style="R")

        embed = discord.Embed(
            title="🎯  Treino Agendado!",
            color=0xD4A843,
        )
        embed.add_field(name="📅  Data e Hora",  value=f"{dt_discord} ({dt_relativo})", inline=False)
        embed.add_field(name="📝  Descrição",    value=descricao,                        inline=False)
        embed.add_field(name="📢  Canal",        value=canal.mention,                   inline=True)
        embed.set_footer(text=f"Agendado por {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)
        print(f"[TREINO] ✅ Treino #{treino['id']} agendado para {data} {hora} por {interaction.user}")

    @treino.error
    async def treino_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "❌ Apenas **Administradores** podem agendar treinos.", ephemeral=True
            )

    # ── /treinos — lista os próximos treinos ──────────────────────────────────
    @app_commands.command(name="treinos", description="Lista os próximos treinos agendados.")
    async def listar_treinos(self, interaction: discord.Interaction):
        treinos = ler("treinos")
        agora   = datetime.now(timezone.utc)

        proximos = [
            t for t in treinos
            if datetime.fromisoformat(t["timestamp"]) > agora
        ]

        if not proximos:
            await interaction.response.send_message(
                "📭 Nenhum treino agendado no momento.", ephemeral=True
            )
            return

        embed = discord.Embed(title="🎯  Próximos Treinos", color=0xD4A843)
        for t in proximos[:5]:
            dt      = datetime.fromisoformat(t["timestamp"])
            relativo = discord.utils.format_dt(dt, style="R")
            embed.add_field(
                name=f"#{t['id']} — {t['data_str']} às {t['hora_str']}",
                value=f"📝 {t['descricao']}\n⏰ {relativo}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    # ── Task: verifica e envia lembretes ──────────────────────────────────────
    @tasks.loop(minutes=1)
    async def verificar_treinos(self):
        await self.bot.wait_until_ready()
        treinos = ler("treinos")
        agora   = datetime.now(timezone.utc)
        alterado = False

        for t in treinos:
            if t["lembrete_enviado"]:
                continue
            dt = datetime.fromisoformat(t["timestamp"])
            diff = (dt - agora).total_seconds()

            # Envia lembrete 30 min antes (janela de 1 min pra não perder)
            if 0 < diff <= 1860:
                canal = self.bot.get_channel(t["canal_id"])
                if canal:
                    dt_discord = discord.utils.format_dt(dt, style="t")
                    embed = discord.Embed(
                        title="⏰  Lembrete de Treino!",
                        description=f"O treino começa em menos de **30 minutos**!",
                        color=0xED4245,
                    )
                    embed.add_field(name="🕐  Horário", value=dt_discord,      inline=True)
                    embed.add_field(name="📝  Descrição", value=t["descricao"], inline=True)
                    embed.set_footer(text="TryHarders RL — Bora treinar! 🚀")
                    await canal.send(embed=embed)
                    print(f"[TREINO] ⏰ Lembrete enviado para treino #{t['id']}")

                t["lembrete_enviado"] = True
                alterado = True

        if alterado:
            salvar("treinos", treinos)


async def setup(bot: commands.Bot):
    await bot.add_cog(Treinos(bot))
