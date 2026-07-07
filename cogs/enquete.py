import discord
from discord.ext import commands
from discord import app_commands
import re

from cogs.backup import ler, salvar

# ─────────────────────────────────────────────
#  Cog: Enquete
#  Arquivo: cogs/enquete.py
#
#  Comando: /enquete (só administradores)
#  Abre um formulário perguntando: tema, opções, se quer mencionar
#  algum cargo (e qual) e se a enquete é privada (voto anônimo,
#  só o placar aparece, ninguém vê quem votou em quê).
# ─────────────────────────────────────────────

EMOJIS_NUMERO = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
MAX_OPCOES = 10


def _emoji(idx: int) -> str:
    return EMOJIS_NUMERO[idx] if idx < len(EMOJIS_NUMERO) else "🔘"


# ─────────────────────────────────────────────
#  Botão de voto (um por opção)
# ─────────────────────────────────────────────
class VotoButton(discord.ui.Button):
    def __init__(self, poll_id: str, idx: int, texto_opcao: str, disabled: bool = False):
        super().__init__(
            label=texto_opcao[:80],
            emoji=_emoji(idx),
            style=discord.ButtonStyle.secondary,
            custom_id=f"enquete_voto_{poll_id}_{idx}",
            disabled=disabled,
            row=idx // 5,
        )
        self.poll_id = poll_id
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        cog: "Enquete" = interaction.client.get_cog("Enquete")
        await cog.registrar_voto(interaction, self.poll_id, self.idx)


# ─────────────────────────────────────────────
#  Botão de encerrar (só admin)
# ─────────────────────────────────────────────
class FecharButton(discord.ui.Button):
    def __init__(self, poll_id: str, disabled: bool = False):
        super().__init__(
            label="Encerrar Enquete",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id=f"enquete_fechar_{poll_id}",
            disabled=disabled,
            row=4,
        )
        self.poll_id = poll_id

    async def callback(self, interaction: discord.Interaction):
        cog: "Enquete" = interaction.client.get_cog("Enquete")
        await cog.encerrar(interaction, self.poll_id)


class EnqueteView(discord.ui.View):
    def __init__(self, poll_id: str, opcoes: list[str], aberta: bool = True):
        super().__init__(timeout=None)
        for idx, opcao in enumerate(opcoes[:MAX_OPCOES]):
            self.add_item(VotoButton(poll_id, idx, opcao, disabled=not aberta))
        self.add_item(FecharButton(poll_id, disabled=not aberta))


# ─────────────────────────────────────────────
#  Modal: criação da enquete
# ─────────────────────────────────────────────
class EnqueteModal(discord.ui.Modal, title="📊 Nova Enquete"):
    tema = discord.ui.TextInput(
        label="Qual o tema da enquete?",
        placeholder="Ex: Qual mapa a gente joga hoje?",
        max_length=200,
    )
    opcoes = discord.ui.TextInput(
        label="Opções (uma por linha, de 2 a 10)",
        style=discord.TextStyle.paragraph,
        placeholder="Sim\nNão\nTalvez",
    )
    mencionar = discord.ui.TextInput(
        label="Mencionar cargo? (nome do cargo, 'todos' ou 'não')",
        placeholder="Ex: Membro / todos / não",
        required=False,
        max_length=100,
    )
    privada = discord.ui.TextInput(
        label="É privada? (sim = voto anônimo / não)",
        placeholder="sim ou não",
        max_length=10,
    )

    def __init__(self, cog: "Enquete"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.criar_enquete(
            interaction,
            self.tema.value,
            self.opcoes.value,
            self.mencionar.value,
            self.privada.value,
        )


# ─────────────────────────────────────────────
#  Cog principal
# ─────────────────────────────────────────────
class Enquete(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.dados = ler("enquetes")  # {mensagem_id_str: {...}}

    # ── Helpers de persistência ──────────────────────────────────
    def _salvar(self):
        salvar("enquetes", self.dados)

    # ── Monta o embed da enquete (placar) ────────────────────────
    def construir_embed(self, poll_id: str) -> discord.Embed:
        registro = self.dados[poll_id]
        opcoes = registro["opcoes"]
        votos: dict = registro["votos"]

        contagem = [0] * len(opcoes)
        for idx in votos.values():
            if 0 <= idx < len(opcoes):
                contagem[idx] += 1
        total = sum(contagem)

        linhas = []
        for i, opcao in enumerate(opcoes):
            qtd = contagem[i]
            pct = (qtd / total * 100) if total else 0
            preenchido = round(pct / 10)
            barra = "▰" * preenchido + "▱" * (10 - preenchido)
            linhas.append(f"{_emoji(i)} **{opcao}** — {qtd} voto(s) ({pct:.0f}%)\n{barra}")

        aberta = registro.get("aberta", True)
        status = "🟢 Aberta" if aberta else "🔴 Encerrada"
        modo = "🔒 Privada — voto anônimo, só o placar aparece" if registro.get("anonima") else "👁️ Pública"

        embed = discord.Embed(
            title=f"📊 {registro['tema']}",
            description="\n\n".join(linhas),
            color=0x5865F2 if aberta else 0x99AAB5,
        )
        embed.set_footer(text=f"{status} • {modo} • {total} voto(s) no total • criada por {registro.get('criador_nome','—')}")
        return embed

    # ── Cria a enquete a partir do modal ─────────────────────────
    async def criar_enquete(self, interaction: discord.Interaction, tema: str, opcoes_raw: str, mencionar_raw: str, privada_raw: str):
        opcoes = [o.strip() for o in re.split(r"[\n,]", opcoes_raw) if o.strip()]

        if len(opcoes) < 2:
            await interaction.response.send_message("❌ Preciso de pelo menos **2 opções** (uma por linha).", ephemeral=True)
            return

        aviso_extra = ""
        if len(opcoes) > MAX_OPCOES:
            opcoes = opcoes[:MAX_OPCOES]
            aviso_extra += f"\n⚠️ Só dá pra ter {MAX_OPCOES} opções, cortei o resto."

        privada = privada_raw.strip().lower() in ("sim", "s", "yes", "y")

        mencionar_valor = mencionar_raw.strip().lower()
        conteudo_mencao = None
        if mencionar_valor in ("", "não", "nao", "n"):
            conteudo_mencao = None
        elif mencionar_valor in ("todos", "everyone", "@everyone"):
            conteudo_mencao = "@everyone"
        else:
            cargo = discord.utils.find(lambda r: r.name.lower() == mencionar_valor, interaction.guild.roles)
            if cargo:
                conteudo_mencao = cargo.mention
            else:
                aviso_extra += f"\n⚠️ Não achei o cargo **{mencionar_raw}**, criei a enquete sem menção."

        await interaction.response.send_message(f"✅ Enquete criada!{aviso_extra}", ephemeral=True)

        embed_provisorio = discord.Embed(title=f"📊 {tema}", description="Carregando...", color=0x5865F2)
        allowed = discord.AllowedMentions(everyone=(conteudo_mencao == "@everyone"), roles=True)
        mensagem = await interaction.channel.send(content=conteudo_mencao, embed=embed_provisorio, allowed_mentions=allowed)

        poll_id = str(mensagem.id)
        self.dados[poll_id] = {
            "tema": tema.strip(),
            "opcoes": opcoes,
            "votos": {},
            "anonima": privada,
            "aberta": True,
            "criador_id": interaction.user.id,
            "criador_nome": str(interaction.user),
            "canal_id": mensagem.channel.id,
            "mensagem_id": mensagem.id,
        }
        self._salvar()

        embed = self.construir_embed(poll_id)
        view = EnqueteView(poll_id, opcoes, aberta=True)
        await mensagem.edit(embed=embed, view=view)

    # ── Registra o voto de quem clicou ───────────────────────────
    async def registrar_voto(self, interaction: discord.Interaction, poll_id: str, idx: int):
        registro = self.dados.get(poll_id)
        if not registro or not registro.get("aberta", True):
            await interaction.response.send_message("❌ Essa enquete já foi encerrada.", ephemeral=True)
            return

        uid = str(interaction.user.id)
        registro["votos"][uid] = idx
        self._salvar()

        embed = self.construir_embed(poll_id)
        view = EnqueteView(poll_id, registro["opcoes"], aberta=True)
        await interaction.response.edit_message(embed=embed, view=view)

        opcao_texto = registro["opcoes"][idx]
        await interaction.followup.send(f"✅ Voto registrado: **{opcao_texto}**", ephemeral=True)

    # ── Encerra a enquete (só admin) ─────────────────────────────
    async def encerrar(self, interaction: discord.Interaction, poll_id: str):
        registro = self.dados.get(poll_id)
        if not registro:
            await interaction.response.send_message("⚠️ Não achei essa enquete.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Só administradores podem encerrar a enquete.", ephemeral=True)
            return

        registro["aberta"] = False
        self._salvar()

        embed = self.construir_embed(poll_id)
        view = EnqueteView(poll_id, registro["opcoes"], aberta=False)
        await interaction.response.edit_message(embed=embed, view=view)

        contagem = [0] * len(registro["opcoes"])
        for idx in registro["votos"].values():
            contagem[idx] += 1

        maior = max(contagem) if contagem else 0
        if maior == 0:
            resultado = f"🔒 Enquete **{registro['tema']}** encerrada por {interaction.user.mention}. Ninguém votou. 😶"
        else:
            vencedoras = [registro["opcoes"][i] for i, qtd in enumerate(contagem) if qtd == maior]
            if len(vencedoras) == 1:
                resultado = f"🔒 Enquete **{registro['tema']}** encerrada por {interaction.user.mention}.\n🏆 Resultado: **{vencedoras[0]}** com {maior} voto(s)!"
            else:
                texto = ", ".join(f"**{v}**" for v in vencedoras)
                resultado = f"🔒 Enquete **{registro['tema']}** encerrada por {interaction.user.mention}.\n🤝 Empate entre {texto} com {maior} voto(s) cada!"

        await interaction.followup.send(resultado)

    # ── Comando /enquete ──────────────────────────────────────────
    @app_commands.command(name="enquete", description="Cria uma enquete (só administradores)")
    async def enquete_cmd(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas **administradores** podem criar enquetes.", ephemeral=True)
            return
        await interaction.response.send_modal(EnqueteModal(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Enquete(bot))
