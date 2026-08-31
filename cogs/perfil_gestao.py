import discord
from discord.ext import commands
from discord import app_commands

from cogs.backup import ler, salvar
from cogs.players import STAFF_IDS

# ─────────────────────────────────────────────
#  Cog: Gestão de Perfil
#  Arquivo: cogs/perfil_gestao.py
#
#  Comandos de Staff para preencher os campos do /perfil (stats.py) que não
#  dão pra descobrir sozinhos a partir do Discord: Título, Divisão,
#  Habilidade (usada pelo /ranking) e MVPs/Destaques de cada jogador.
#
#  Tudo isso mexe no mesmo data/perfis.json usado por cogs/stats.py e
#  cogs/medalhas.py — por isso todo campo novo é sempre .setdefault(), pra
#  nunca sobrescrever o que os outros cogs já guardaram ali.
# ─────────────────────────────────────────────

MAX_DESTAQUES_GUARDADOS = 20


def eh_staff_do_clube(membro: discord.Member) -> bool:
    """Staff = tem um dos cargos de liderança do clube (mesma lista usada
    no painel de jogadores em cogs/players.py) ou é Administrador."""
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_IDS for r in membro.roles)


def _garantir_perfil(sid: str, nome: str, perfis: dict) -> dict:
    if sid not in perfis:
        perfis[sid] = {"nome": nome, "amistosos": 0, "vitorias": 0, "derrotas": 0}
    dados = perfis[sid]
    dados.setdefault("amistosos", 0)
    dados.setdefault("vitorias", 0)
    dados.setdefault("derrotas", 0)
    dados.setdefault("divisao", None)
    dados.setdefault("titulo", None)
    dados.setdefault("habilidade", None)
    dados.setdefault("mvps", 0)
    dados.setdefault("destaques", [])
    return dados


class PerfilGestao(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _checar_staff(self, interaction: discord.Interaction) -> bool:
        if not eh_staff_do_clube(interaction.user):
            await interaction.response.send_message(
                "❌ Apenas **Staff** do clube pode usar este comando.", ephemeral=True
            )
            return False
        return True

    # ── /perfil-editar — título, divisão e habilidade num único comando ─────
    @app_commands.command(name="perfil-editar", description="[Staff] Edita título, divisão e/ou habilidade de um jogador.")
    @app_commands.describe(
        membro="Jogador a editar",
        titulo="Novo título (deixe vazio para não alterar, escreva 'remover' para limpar)",
        divisao="Nova divisão, ex: 'I', 'II', 'III' (escreva 'remover' para limpar)",
        habilidade="Nota de habilidade de 0 a 100, usada no /ranking (escreva 'remover' para limpar)",
    )
    async def perfil_editar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        titulo: str = None,
        divisao: str = None,
        habilidade: str = None,
    ):
        if not await self._checar_staff(interaction):
            return

        if titulo is None and divisao is None and habilidade is None:
            await interaction.response.send_message(
                "⚠️ Informe pelo menos um campo pra alterar (`titulo`, `divisao` ou `habilidade`).",
                ephemeral=True,
            )
            return

        perfis = ler("perfis")
        dados = _garantir_perfil(str(membro.id), membro.display_name, perfis)

        alterado = []
        if titulo is not None:
            dados["titulo"] = None if titulo.strip().lower() in ("remover", "limpar", "") else titulo.strip()
            alterado.append(f"🏵️ Título → **{dados['titulo'] or '—'}**")

        if divisao is not None:
            dados["divisao"] = None if divisao.strip().lower() in ("remover", "limpar", "") else divisao.strip()
            alterado.append(f"🎚️ Divisão → **{dados['divisao'] or '—'}**")

        if habilidade is not None:
            if habilidade.strip().lower() in ("remover", "limpar", ""):
                dados["habilidade"] = None
                alterado.append("📈 Habilidade → **—**")
            else:
                try:
                    valor = int(habilidade.strip())
                except ValueError:
                    await interaction.response.send_message(
                        "❌ `habilidade` precisa ser um número de 0 a 100 (ou 'remover').", ephemeral=True
                    )
                    return
                if not (0 <= valor <= 100):
                    await interaction.response.send_message(
                        "❌ `habilidade` precisa estar entre 0 e 100.", ephemeral=True
                    )
                    return
                dados["habilidade"] = valor
                alterado.append(f"📈 Habilidade → **{valor}**")

        salvar("perfis", perfis)

        await interaction.response.send_message(
            f"✅ Perfil de **{membro.display_name}** atualizado:\n" + "\n".join(alterado),
            ephemeral=True,
        )
        print(f"[PERFIL_GESTAO] ✏️ {interaction.user} editou o perfil de {membro}: {alterado}")

    # ── /mvp — soma 1 MVP e avisa publicamente ──────────────────────────────
    @app_commands.command(name="mvp", description="[Staff] Dá um MVP a um jogador.")
    @app_commands.describe(membro="Jogador que foi MVP", motivo="Motivo/partida (opcional, aparece no anúncio)")
    async def mvp(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = ""):
        if not await self._checar_staff(interaction):
            return

        perfis = ler("perfis")
        dados = _garantir_perfil(str(membro.id), membro.display_name, perfis)
        dados["mvps"] += 1
        total = dados["mvps"]
        salvar("perfis", perfis)

        embed = discord.Embed(
            title="🌟 MVP!",
            description=f"{membro.mention} foi eleito **MVP**!" + (f"\n_{motivo}_" if motivo else ""),
            color=0xD4A843,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=f"Total de MVPs: {total}  •  Dado por {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)
        print(f"[PERFIL_GESTAO] 🌟 {interaction.user} deu MVP para {membro} (total: {total})")

    # ── /destaque-adicionar / /destaque-remover / /destaques ────────────────
    @app_commands.command(name="destaque-adicionar", description="[Staff] Adiciona um destaque ao perfil de um jogador.")
    @app_commands.describe(membro="Jogador", texto="Texto curto do destaque (ex: 'Hat-trick contra X FC')")
    async def destaque_adicionar(self, interaction: discord.Interaction, membro: discord.Member, texto: str):
        if not await self._checar_staff(interaction):
            return

        texto = texto.strip()
        if not texto:
            await interaction.response.send_message("❌ O destaque não pode estar vazio.", ephemeral=True)
            return

        perfis = ler("perfis")
        dados = _garantir_perfil(str(membro.id), membro.display_name, perfis)
        dados["destaques"].append(texto[:200])
        dados["destaques"] = dados["destaques"][-MAX_DESTAQUES_GUARDADOS:]
        salvar("perfis", perfis)

        await interaction.response.send_message(
            f"✅ Destaque adicionado ao perfil de **{membro.display_name}**:\n⭐ {texto[:200]}",
            ephemeral=True,
        )
        print(f"[PERFIL_GESTAO] ⭐ {interaction.user} adicionou destaque a {membro}: {texto}")

    @app_commands.command(name="destaque-remover", description="[Staff] Remove um destaque do perfil de um jogador (veja /destaques primeiro).")
    @app_commands.describe(membro="Jogador", numero="Número do destaque (veja com /destaques)")
    async def destaque_remover(self, interaction: discord.Interaction, membro: discord.Member, numero: int):
        if not await self._checar_staff(interaction):
            return

        perfis = ler("perfis")
        dados = _garantir_perfil(str(membro.id), membro.display_name, perfis)
        destaques = dados["destaques"]

        if not (1 <= numero <= len(destaques)):
            await interaction.response.send_message(
                f"❌ Número inválido. Use `/destaques` pra ver os destaques de **{membro.display_name}** "
                f"e o número certo (`1` a `{len(destaques)}`).",
                ephemeral=True,
            )
            return

        removido = destaques.pop(numero - 1)
        salvar("perfis", perfis)

        await interaction.response.send_message(
            f"🗑️ Destaque removido do perfil de **{membro.display_name}**: ⭐ {removido}",
            ephemeral=True,
        )
        print(f"[PERFIL_GESTAO] 🗑️ {interaction.user} removeu destaque de {membro}: {removido}")

    @app_commands.command(name="destaques", description="Lista os destaques de um jogador com os números pra remover.")
    @app_commands.describe(membro="Jogador (deixe vazio para ver os seus)")
    async def destaques_cmd(self, interaction: discord.Interaction, membro: discord.Member = None):
        membro = membro or interaction.user
        perfis = ler("perfis")
        dados = _garantir_perfil(str(membro.id), membro.display_name, perfis)
        salvar("perfis", perfis)

        destaques = dados["destaques"]
        if not destaques:
            texto = "_Nenhum destaque registrado ainda._"
        else:
            texto = "\n".join(f"`{i}.` ⭐ {d}" for i, d in enumerate(destaques, start=1))

        embed = discord.Embed(title=f"⭐ Destaques de {membro.display_name}", description=texto, color=0xD4A843)
        await interaction.response.send_message(embed=embed)

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
    await bot.add_cog(PerfilGestao(bot))
