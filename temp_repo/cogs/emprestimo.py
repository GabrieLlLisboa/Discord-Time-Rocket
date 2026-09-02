import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler, salvar, agora_str
from cogs.players import STAFF_IDS
from cogs.paginacao import paginar, PaginacaoView

# ─────────────────────────────────────────────
#  Cog: Empréstimos
#  Arquivo: cogs/emprestimo.py
#
#  Registra jogadores da TryHarders emprestados para outros clubes:
#  quem, pra onde, quando começa/termina, quantas partidas já disputou por
#  lá e o status atual do empréstimo. Guardado em data/emprestimos.json
#  (lista de registros, cada um com "id" incremental).
# ─────────────────────────────────────────────

STATUS_INFO = {
    "ativo":     ("🟢", "Ativo"),
    "encerrado": ("⚪", "Encerrado"),
    "cancelado": ("🔴", "Cancelado"),
}


def eh_staff_do_clube(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


def _proximo_id(registros: list) -> int:
    return (max((r["id"] for r in registros), default=0)) + 1


def _formatar_registro(r: dict) -> discord.Embed:
    emoji, label = STATUS_INFO.get(r["status"], ("❓", r["status"]))
    embed = discord.Embed(
        title=f"📄 Empréstimo `#{r['id']}` — {r['jogador_nome']}",
        color=0xD4A843,
    )
    embed.add_field(name="🏟️  Clube de destino", value=r["clube_destino"], inline=True)
    embed.add_field(name="📌  Status",            value=f"{emoji} {label}",  inline=True)
    embed.add_field(name="🎮  Partidas disputadas", value=f"`{r['partidas_disputadas']}`", inline=True)
    embed.add_field(name="📅  Início",   value=r["data_inicio"],  inline=True)
    embed.add_field(name="🏁  Término",  value=r["data_termino"], inline=True)
    embed.set_footer(text=f"Registrado por {r['registrado_por']} em {r['criado_em']}")
    return embed


class Emprestimo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _checar_staff(self, interaction: discord.Interaction) -> bool:
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode gerenciar empréstimos.", ephemeral=True
            )
            return False
        return True

    # ── /emprestimo-registrar ────────────────────────────────────────────
    @app_commands.command(name="emprestimo-registrar", description="[Staff] Registra o empréstimo de um jogador para outro clube.")
    @app_commands.describe(
        jogador="Jogador emprestado",
        clube_destino="Nome do clube que vai receber o jogador",
        data_inicio="Data de início (ex: 01/09/2026)",
        data_termino="Data prevista de término (ex: 01/12/2026)",
    )
    async def emprestimo_registrar(
        self,
        interaction: discord.Interaction,
        jogador: discord.Member,
        clube_destino: str,
        data_inicio: str,
        data_termino: str,
    ):
        if not await self._checar_staff(interaction):
            return

        emprestimos = ler("emprestimos")
        registro = {
            "id":                  _proximo_id(emprestimos),
            "jogador_id":          jogador.id,
            "jogador_nome":        jogador.display_name,
            "clube_destino":       clube_destino.strip(),
            "data_inicio":         data_inicio.strip(),
            "data_termino":        data_termino.strip(),
            "partidas_disputadas": 0,
            "status":              "ativo",
            "registrado_por":      interaction.user.display_name,
            "criado_em":           agora_str(),
        }
        emprestimos.append(registro)
        salvar("emprestimos", emprestimos)

        embed = _formatar_registro(registro)
        embed.title = "✅ Empréstimo registrado — " + embed.title.split("— ", 1)[1]
        await interaction.response.send_message(embed=embed)
        print(f"[EMPRESTIMO] ✅ {interaction.user} registrou empréstimo #{registro['id']} de {jogador} para {clube_destino}")

    # ── /emprestimo-atualizar ────────────────────────────────────────────
    @app_commands.command(name="emprestimo-atualizar", description="[Staff] Atualiza partidas disputadas e/ou status de um empréstimo.")
    @app_commands.describe(
        id="ID do empréstimo (veja com /emprestimos)",
        partidas_disputadas="Novo total de partidas disputadas no clube de destino",
        status="Novo status do empréstimo",
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Ativo",     value="ativo"),
        app_commands.Choice(name="⚪ Encerrado", value="encerrado"),
        app_commands.Choice(name="🔴 Cancelado", value="cancelado"),
    ])
    async def emprestimo_atualizar(
        self,
        interaction: discord.Interaction,
        id: int,
        partidas_disputadas: int = None,
        status: app_commands.Choice[str] = None,
    ):
        if not await self._checar_staff(interaction):
            return

        if partidas_disputadas is None and status is None:
            await interaction.response.send_message(
                "⚠️ Informe `partidas_disputadas` e/ou `status` pra atualizar.", ephemeral=True
            )
            return

        emprestimos = ler("emprestimos")
        registro = next((r for r in emprestimos if r["id"] == id), None)
        if registro is None:
            await interaction.response.send_message(f"❌ Não achei o empréstimo `#{id}`.", ephemeral=True)
            return

        if partidas_disputadas is not None:
            if partidas_disputadas < 0:
                await interaction.response.send_message("❌ `partidas_disputadas` não pode ser negativo.", ephemeral=True)
                return
            registro["partidas_disputadas"] = partidas_disputadas
        if status is not None:
            registro["status"] = status.value

        salvar("emprestimos", emprestimos)

        embed = _formatar_registro(registro)
        embed.title = "✏️ Empréstimo atualizado — " + embed.title.split("— ", 1)[1]
        await interaction.response.send_message(embed=embed)
        print(f"[EMPRESTIMO] ✏️ {interaction.user} atualizou o empréstimo #{id}")

    # ── /emprestimos — lista/filtra ──────────────────────────────────────
    @app_commands.command(name="emprestimos", description="Lista os empréstimos registrados.")
    @app_commands.describe(jogador="Filtrar por jogador (opcional)", status="Filtrar por status (opcional)")
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Ativo",     value="ativo"),
        app_commands.Choice(name="⚪ Encerrado", value="encerrado"),
        app_commands.Choice(name="🔴 Cancelado", value="cancelado"),
    ])
    async def emprestimos_cmd(
        self,
        interaction: discord.Interaction,
        jogador: discord.Member = None,
        status: app_commands.Choice[str] = None,
    ):
        emprestimos = ler("emprestimos")

        if jogador is not None:
            emprestimos = [r for r in emprestimos if r["jogador_id"] == jogador.id]
        if status is not None:
            emprestimos = [r for r in emprestimos if r["status"] == status.value]

        if not emprestimos:
            await interaction.response.send_message("📭 Nenhum empréstimo encontrado com esse filtro.", ephemeral=True)
            return

        emprestimos = sorted(emprestimos, key=lambda r: r["id"], reverse=True)

        def montar_pagina(pagina, total, fatia, offset):
            embed = discord.Embed(title="📄 Empréstimos — TryHarders RL", color=0xD4A843)
            for r in fatia:
                emoji, label = STATUS_INFO.get(r["status"], ("❓", r["status"]))
                embed.add_field(
                    name=f"`#{r['id']}` {r['jogador_nome']} → {r['clube_destino']}",
                    value=(
                        f"{emoji} {label}  •  🎮 `{r['partidas_disputadas']}` partidas\n"
                        f"📅 {r['data_inicio']} até {r['data_termino']}"
                    ),
                    inline=False,
                )
            embed.set_footer(text=f"Página {pagina}/{total}  •  {len(emprestimos)} empréstimo(s) no total")
            return embed

        embeds = paginar(emprestimos, 5, montar_pagina)
        view = PaginacaoView(embeds) if len(embeds) > 1 else None
        await interaction.response.send_message(embed=embeds[0], view=view)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = f"❌ Erro: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Emprestimo(bot))
