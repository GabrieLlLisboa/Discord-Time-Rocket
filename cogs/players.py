"""
cogs/players.py  –  Sistema de Achar Dupla
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import string
import time
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ──────────────────────────────────────────────
#  Persistência simples em JSON
# ──────────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def _load(name: str):
    p = DATA_DIR / f"{name}.json"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {} if name in ("perfis", "reputacoes") else []

def _save(name: str, obj):
    p = DATA_DIR / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ──────────────────────────────────────────────
#  Ranks do Rocket League
# ──────────────────────────────────────────────
RANKS = [
    "Bronze I", "Bronze II", "Bronze III",
    "Silver I", "Silver II", "Silver III",
    "Gold I", "Gold II", "Gold III",
    "Platinum I", "Platinum II", "Platinum III",
    "Diamond I", "Diamond II", "Diamond III",
    "Champion I", "Champion II", "Champion III",
    "Grand Champion I", "Grand Champion II", "Grand Champion III",
    "Supersonic Legend",
]

RANK_INDEX = {r: i for i, r in enumerate(RANKS)}

def _ranks_compativeis(rank: str, preferencia: str) -> list:
    idx = RANK_INDEX.get(rank, 0)
    if preferencia == "mesmo":
        return [rank]
    if preferencia == "±1":
        return [RANKS[i] for i in range(max(0, idx - 1), min(len(RANKS), idx + 2))]
    return RANKS

def _estrelas(valor: float) -> str:
    cheia = int(valor)
    metade = valor % 1 >= 0.5
    return "⭐" * cheia + ("✨" if metade else "") + "☆" * (5 - cheia - (1 if metade else 0))

# ──────────────────────────────────────────────
#  Modal: Criar Perfil
# ──────────────────────────────────────────────
class PerfilModal(discord.ui.Modal, title="Criar Perfil"):
    nick = discord.ui.TextInput(
        label="Seu nick no Rocket League",
        placeholder="Ex: TryHarder#2847",
        max_length=64,
    )
    microfone = discord.ui.TextInput(
        label="Tem microfone? (Sim / Não)",
        placeholder="Sim ou Não",
        max_length=3,
    )

    def __init__(self, cog: "Players"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        mic = self.microfone.value.strip().lower() in ("sim", "s", "yes", "y")
        nick = self.nick.value.strip()
        rank = await self.cog._fetch_rank(nick)

        perfis = _load("perfis")
        uid = str(interaction.user.id)
        perfis[uid] = {
            "nick": nick,
            "microfone": mic,
            "rank": rank,
            "usuario": str(interaction.user),
            "criado_em": int(time.time()),
        }
        _save("perfis", perfis)

        reputacoes = _load("reputacoes")
        rep = reputacoes.get(uid, {"total": 0, "count": 0, "toxico": 0})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        embed = discord.Embed(
            title="✅ Perfil criado com sucesso!",
            color=0xD4A843,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="🎮 Nick", value=nick, inline=True)
        embed.add_field(name="🏆 Rank", value=rank, inline=True)
        embed.add_field(name="🎙️ Microfone", value="Sim ✅" if mic else "Não ❌", inline=True)
        embed.add_field(name="⭐ Reputação", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.set_footer(text="Use /perfil para ver seu perfil completo.")

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
#  View: Botão que abre o Modal de Perfil
# ──────────────────────────────────────────────
class PerfilView(discord.ui.View):
    def __init__(self, cog: "Players"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="📋 Registrar Perfil",
        style=discord.ButtonStyle.primary,
        custom_id="abrir_modal_perfil",
    )
    async def abrir_perfil(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PerfilModal(self.cog))


# ──────────────────────────────────────────────
#  Modal: Procurar Dupla
# ──────────────────────────────────────────────
class DuplaModal(discord.ui.Modal, title="Procurar Dupla"):
    modo = discord.ui.TextInput(
        label="Modo (2v2 / 3v3 / 1v1 / Private)",
        placeholder="2v2",
        max_length=10,
    )
    objetivo = discord.ui.TextInput(
        label="Objetivo (Rankear / Casual / Treinar)",
        placeholder="Rankear",
        max_length=10,
    )
    mic_req = discord.ui.TextInput(
        label="Microfone (Obrigatório / Tanto faz)",
        placeholder="Tanto faz",
        max_length=12,
    )
    rank_pref = discord.ui.TextInput(
        label="Rank procurado (mesmo / ±1 / qualquer)",
        placeholder="mesmo",
        max_length=8,
    )

    def __init__(self, cog: "Players"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        perfis = _load("perfis")

        if uid not in perfis:
            await interaction.response.send_message(
                "⚠️ Você precisa criar seu perfil primeiro com `!setuperfil`.",
                ephemeral=True,
            )
            return

        perfil = perfis[uid]
        mic_val = self.mic_req.value.strip().lower()
        rank_pref_val = self.rank_pref.value.strip().lower()
        mic_obrigatorio = mic_val in ("obrigatório", "obrigatorio", "sim", "s")
        rank_pref_norm = "mesmo" if "mesmo" in rank_pref_val else ("±1" if "1" in rank_pref_val else "qualquer")

        fila = _load("fila")
        fila = [f for f in fila if f["uid"] != uid]

        fila.append({
            "uid": uid,
            "nick": perfil["nick"],
            "rank": perfil["rank"],
            "microfone": perfil["microfone"],
            "modo": self.modo.value.strip(),
            "objetivo": self.objetivo.value.strip(),
            "mic_obrigatorio": mic_obrigatorio,
            "rank_pref": rank_pref_norm,
            "entrou_em": int(time.time()),
            "ultimo_ping": int(time.time()),
        })
        _save("fila", fila)

        reputacoes = _load("reputacoes")
        rep = reputacoes.get(uid, {"total": 0, "count": 0})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        embed = discord.Embed(
            title="🔍 Procurando dupla…",
            description="Você entrou na fila! Aguarde enquanto buscamos alguém compatível.",
            color=0x5865F2,
        )
        embed.add_field(name="🏆 Seu Rank", value=perfil["rank"], inline=True)
        embed.add_field(name="🎮 Modo", value=self.modo.value.strip(), inline=True)
        embed.add_field(name="🎯 Objetivo", value=self.objetivo.value.strip(), inline=True)
        embed.add_field(name="🎙️ Mic req.", value="Obrigatório" if mic_obrigatorio else "Tanto faz", inline=True)
        embed.add_field(name="🔎 Rank procurado", value=rank_pref_norm, inline=True)
        embed.add_field(name="⭐ Sua rep.", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.set_footer(text="A cada 30 min você receberá uma confirmação no PV.")

        await interaction.response.send_message(embed=embed, ephemeral=True)
        asyncio.create_task(self.cog._tentar_match(interaction.guild))


# ──────────────────────────────────────────────
#  View: Botão que abre o Modal de Dupla
# ──────────────────────────────────────────────
class DuplaView(discord.ui.View):
    def __init__(self, cog: "Players"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🔍 Procurar Dupla",
        style=discord.ButtonStyle.success,
        custom_id="abrir_modal_dupla",
    )
    async def abrir_dupla(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DuplaModal(self.cog))


# ──────────────────────────────────────────────
#  View: Convite de Match (2 minutos)
# ──────────────────────────────────────────────
class ConviteView(discord.ui.View):
    def __init__(self, cog: "Players", match_id: str, uid_a: str, uid_b: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.match_id = match_id
        self.uid_a = uid_a
        self.uid_b = uid_b
        self.respostas: dict = {}

    async def _verificar(self, interaction: discord.Interaction):
        if len(self.respostas) < 2:
            return
        if all(self.respostas.values()):
            await self.cog._criar_canal_match(interaction.guild, self.match_id, self.uid_a, self.uid_b)
        else:
            for uid, aceitou in self.respostas.items():
                if aceitou:
                    await self.cog._reinserir_fila(uid)
            for uid in self.respostas:
                try:
                    user = await self.cog.bot.fetch_user(int(uid))
                    await user.send("❌ Um dos jogadores recusou o match. Voltando à fila…")
                except Exception:
                    pass
        self.stop()

    @discord.ui.button(label="✅ Aceitar", style=discord.ButtonStyle.success)
    async def aceitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid not in (self.uid_a, self.uid_b):
            return
        self.respostas[uid] = True
        await interaction.response.edit_message(content="✅ Você aceitou! Aguardando o outro jogador…", view=None)
        await self._verificar(interaction)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid not in (self.uid_a, self.uid_b):
            return
        self.respostas[uid] = False
        await interaction.response.edit_message(content="❌ Você recusou o match.", view=None)
        await self._verificar(interaction)

    async def on_timeout(self):
        fila = _load("fila")
        perfis = _load("perfis")
        for uid in (self.uid_a, self.uid_b):
            if uid not in self.respostas:
                try:
                    user = await self.cog.bot.fetch_user(int(uid))
                    await user.send("⏰ Tempo esgotado! Você não respondeu ao convite e foi removido da fila.")
                except Exception:
                    pass


# ──────────────────────────────────────────────
#  Modal: Avaliação pós-partida
# ──────────────────────────────────────────────
class AvaliacaoModal(discord.ui.Modal):
    def __init__(self, cog: "Players", avaliado_uid: str, avaliado_nick: str):
        super().__init__(title=f"Avaliar {avaliado_nick}")
        self.cog = cog
        self.avaliado_uid = avaliado_uid

        self.toxico = discord.ui.TextInput(label="Foi tóxico? (Sim / Não)", placeholder="Não", max_length=3)
        self.estrelas = discord.ui.TextInput(label="Reputação (1 a 5 estrelas)", placeholder="5", max_length=1)
        self.add_item(self.toxico)
        self.add_item(self.estrelas)

    async def on_submit(self, interaction: discord.Interaction):
        toxico = self.toxico.value.strip().lower() in ("sim", "s")
        try:
            nota = max(1, min(5, int(self.estrelas.value.strip())))
        except ValueError:
            nota = 5

        reputacoes = _load("reputacoes")
        rep = reputacoes.get(self.avaliado_uid, {"total": 0, "count": 0, "toxico": 0, "melhor_parceiro": {}})
        rep["total"] += nota
        rep["count"] += 1
        if toxico:
            rep["toxico"] += 1
        mp = rep.get("melhor_parceiro", {})
        mp[str(interaction.user.id)] = mp.get(str(interaction.user.id), 0) + nota
        rep["melhor_parceiro"] = mp
        reputacoes[self.avaliado_uid] = rep
        _save("reputacoes", reputacoes)

        avg = round(rep["total"] / rep["count"], 1)
        await interaction.response.send_message(
            f"✅ Avaliação registrada! {_estrelas(avg)} — Obrigado pelo feedback.", ephemeral=True
        )


class AvaliacaoView(discord.ui.View):
    def __init__(self, cog: "Players", avaliado_uid: str, avaliado_nick: str):
        super().__init__(timeout=3600)
        self.cog = cog
        self.avaliado_uid = avaliado_uid
        self.avaliado_nick = avaliado_nick

    @discord.ui.button(label="⭐ Avaliar parceiro", style=discord.ButtonStyle.primary)
    async def avaliar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AvaliacaoModal(self.cog, self.avaliado_uid, self.avaliado_nick))
        self.stop()


# ──────────────────────────────────────────────
#  View: Confirmação de atividade no PV
# ──────────────────────────────────────────────
class AtividadeView(discord.ui.View):
    def __init__(self, cog: "Players", uid: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.uid = uid
        self.respondeu = False

    @discord.ui.button(label="✅ Sim, ainda procuro", style=discord.ButtonStyle.success)
    async def sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid:
            return
        self.respondeu = True
        fila = _load("fila")
        for f in fila:
            if f["uid"] == self.uid:
                f["ultimo_ping"] = int(time.time())
        _save("fila", fila)
        await interaction.response.edit_message(content="✅ Ótimo! Continuamos procurando sua dupla.", view=None)
        self.stop()

    @discord.ui.button(label="❌ Não, pode me remover", style=discord.ButtonStyle.danger)
    async def nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid:
            return
        self.respondeu = True
        fila = _load("fila")
        fila = [f for f in fila if f["uid"] != self.uid]
        _save("fila", fila)
        await interaction.response.edit_message(
            content="👋 Você foi removido da fila. Use `!setupdupla` quando quiser procurar novamente.", view=None
        )
        self.stop()

    async def on_timeout(self):
        if not self.respondeu:
            fila = _load("fila")
            fila = [f for f in fila if f["uid"] != self.uid]
            _save("fila", fila)


# ──────────────────────────────────────────────
#  Cog Principal
# ──────────────────────────────────────────────
class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificar_atividade.start()
        self.atualizar_ranks.start()

    def cog_unload(self):
        self.verificar_atividade.cancel()
        self.atualizar_ranks.cancel()

    async def _fetch_rank(self, nick: str) -> str:
        """
        Busca rank via Tracker Network. Por enquanto retorna placeholder.
        Para integrar de verdade, descomente o bloco httpx abaixo
        e adicione TRN_API_KEY no seu .env
        """
        # import httpx
        # url = f"https://api.tracker.gg/api/v2/rocket-league/standard/profile/epic/{nick}"
        # headers = {"TRN-Api-Key": os.getenv("TRN_API_KEY", "")}
        # async with httpx.AsyncClient() as client:
        #     r = await client.get(url, headers=headers, timeout=10)
        #     if r.status_code == 200:
        #         data = r.json()
        #         # extraia o rank aqui conforme a resposta da API
        #         ...
        return "Gold II"  # placeholder

    async def _tentar_match(self, guild: discord.Guild):
        await asyncio.sleep(1)
        fila = _load("fila")
        if len(fila) < 2:
            return

        fila.sort(key=lambda x: x["entrou_em"])
        used = set()
        matched = []

        for i, a in enumerate(fila):
            if a["uid"] in used:
                continue
            for b in fila[i + 1:]:
                if b["uid"] in used:
                    continue
                if self._sao_compativeis(a, b):
                    matched.append((a, b))
                    used.add(a["uid"])
                    used.add(b["uid"])
                    break

        if not matched:
            return

        fila = [f for f in fila if f["uid"] not in used]
        _save("fila", fila)

        for a, b in matched:
            match_id = "".join(random.choices(string.digits, k=4))
            await self._enviar_convite(guild, match_id, a, b)

    def _sao_compativeis(self, a: dict, b: dict) -> bool:
        if a["modo"].lower() != b["modo"].lower():
            return False
        if a["objetivo"].lower() != b["objetivo"].lower():
            return False
        if a["mic_obrigatorio"] and not b["microfone"]:
            return False
        if b["mic_obrigatorio"] and not a["microfone"]:
            return False
        ranks_a = _ranks_compativeis(a["rank"], a["rank_pref"])
        ranks_b = _ranks_compativeis(b["rank"], b["rank_pref"])
        return b["rank"] in ranks_a and a["rank"] in ranks_b

    async def _enviar_convite(self, guild: discord.Guild, match_id: str, a: dict, b: dict):
        reputacoes = _load("reputacoes")

        def rep_str(uid):
            rep = reputacoes.get(uid, {"total": 0, "count": 0})
            avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0
            return f"{_estrelas(avg)} ({avg}/5.0)"

        view = ConviteView(self, match_id, a["uid"], b["uid"])

        for jogador, oponente in [(a, b), (b, a)]:
            try:
                user = await self.bot.fetch_user(int(jogador["uid"]))
                embed = discord.Embed(
                    title="🎮 Dupla encontrada!",
                    description="Você tem **2 minutos** para aceitar ou recusar.",
                    color=0x57F287,
                )
                embed.add_field(name="👤 Parceiro", value=oponente["nick"], inline=True)
                embed.add_field(name="🏆 Rank", value=oponente["rank"], inline=True)
                embed.add_field(name="⭐ Reputação", value=rep_str(oponente["uid"]), inline=True)
                embed.add_field(name="🎮 Modo", value=jogador["modo"], inline=True)
                embed.add_field(name="🎯 Objetivo", value=jogador["objetivo"], inline=True)
                await user.send(embed=embed, view=view)
            except Exception as e:
                print(f"[PLAYERS] Erro ao DM {jogador['uid']}: {e}")

    async def _reinserir_fila(self, uid: str):
        try:
            user = await self.bot.fetch_user(int(uid))
            await user.send("🔄 Você foi reinserido na fila. Procurando nova dupla…")
        except Exception:
            pass

    async def _criar_canal_match(self, guild: discord.Guild, match_id: str, uid_a: str, uid_b: str):
        perfis = _load("perfis")
        pa = perfis.get(uid_a, {})
        pb = perfis.get(uid_b, {})

        try:
            member_a = guild.get_member(int(uid_a)) or await guild.fetch_member(int(uid_a))
            member_b = guild.get_member(int(uid_b)) or await guild.fetch_member(int(uid_b))
        except Exception as e:
            print(f"[PLAYERS] Erro ao buscar membros: {e}")
            return

        categoria = await guild.create_category(
            name=f"MATCH-{match_id}",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member_a: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
                member_b: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
            },
        )

        chat = await guild.create_text_channel("💬︱chat", category=categoria)
        await guild.create_voice_channel("🔊︱voz", category=categoria)

        reputacoes = _load("reputacoes")
        def rep_avg(uid):
            rep = reputacoes.get(uid, {"total": 0, "count": 0})
            return round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        embed = discord.Embed(title="✅ Dupla Encontrada!", color=0xD4A843)
        embed.add_field(
            name=f"Jogador 1 — {pa.get('nick', uid_a)}",
            value=f"🏆 {pa.get('rank', '?')} | ⭐ {rep_avg(uid_a)}/5.0",
            inline=False,
        )
        embed.add_field(
            name=f"Jogador 2 — {pb.get('nick', uid_b)}",
            value=f"🏆 {pb.get('rank', '?')} | ⭐ {rep_avg(uid_b)}/5.0",
            inline=False,
        )
        embed.set_footer(text=f"Boa partida! • MATCH-{match_id}")

        await chat.send(content=f"{member_a.mention} {member_b.mention}", embed=embed)

        matches = _load("matches")
        matches.append({
            "match_id": match_id,
            "uid_a": uid_a,
            "uid_b": uid_b,
            "criado_em": int(time.time()),
            "categoria_id": categoria.id,
            "avaliado": False,
        })
        _save("matches", matches)

        asyncio.create_task(self._agendar_avaliacao(match_id, uid_a, uid_b, pa, pb, 3600))

    async def _agendar_avaliacao(self, match_id, uid_a, uid_b, pa, pb, delay_s):
        await asyncio.sleep(delay_s)

        await self._pedir_avaliacao(uid_a, uid_b, pb.get("nick", uid_b))
        await self._pedir_avaliacao(uid_b, uid_a, pa.get("nick", uid_a))

        matches = _load("matches")
        for m in matches:
            if m["match_id"] == match_id:
                try:
                    cat = self.bot.get_channel(m["categoria_id"])
                    if cat:
                        for ch in cat.channels:
                            await ch.delete()
                        await cat.delete()
                except Exception:
                    pass
                m["avaliado"] = True
        _save("matches", matches)

    async def _pedir_avaliacao(self, avaliador_uid, avaliado_uid, avaliado_nick):
        try:
            user = await self.bot.fetch_user(int(avaliador_uid))
            view = AvaliacaoView(self, avaliado_uid, avaliado_nick)
            await user.send(
                f"🎮 Sua partida com **{avaliado_nick}** terminou!\nComo foi jogar com ele?",
                view=view,
            )
        except Exception as e:
            print(f"[PLAYERS] Erro ao pedir avaliação: {e}")

    # ── Task: Verificar atividade a cada 30 min ──
    @tasks.loop(minutes=30)
    async def verificar_atividade(self):
        fila = _load("fila")
        for entrada in list(fila):
            uid = entrada["uid"]
            try:
                user = await self.bot.fetch_user(int(uid))
                view = AtividadeView(self, uid)
                await user.send(
                    "⏰ Você ainda está procurando dupla?\n"
                    "Se não responder em **10 minutos**, será removido da fila automaticamente.",
                    view=view,
                )
            except Exception as e:
                print(f"[PLAYERS] Erro ao pingar {uid}: {e}")

    @verificar_atividade.before_loop
    async def before_verificar(self):
        await self.bot.wait_until_ready()

    # ── Task: Atualizar ranks a cada 6h ─────────
    @tasks.loop(hours=6)
    async def atualizar_ranks(self):
        perfis = _load("perfis")
        for uid, perfil in perfis.items():
            perfil["rank"] = await self._fetch_rank(perfil.get("nick", ""))
        _save("perfis", perfis)
        print("[PLAYERS] ✅ Ranks atualizados.")

    @atualizar_ranks.before_loop
    async def before_ranks(self):
        await self.bot.wait_until_ready()

    # ──────────────────────────────────────────────
    #  Comandos com prefixo (!)
    # ──────────────────────────────────────────────
    @commands.command(name="setuperfil")
    async def setuperfil(self, ctx: commands.Context):
        """Manda a mensagem com botão para criar perfil."""
        embed = discord.Embed(
            title="📋 Registre seu perfil",
            description=(
                "Clique no botão abaixo para preencher seu nick e informações.\n"
                "O bot irá puxar seu rank automaticamente!"
            ),
            color=0xD4A843,
        )
        embed.set_footer(text="Seus dados ficam salvos — só precisa fazer isso uma vez.")
        await ctx.send(embed=embed, view=PerfilView(self))

    @commands.command(name="setupdupla")
    async def setupdupla(self, ctx: commands.Context):
        """Manda a mensagem com botão para procurar dupla."""
        embed = discord.Embed(
            title="🔍 Procure uma dupla",
            description=(
                "Clique no botão abaixo para informar seu modo, objetivo e preferências.\n"
                "Assim que encontrarmos alguém compatível, você recebe um aviso no PV!"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="A cada 30 min confirmaremos se você ainda está na fila.")
        await ctx.send(embed=embed, view=DuplaView(self))

    @commands.command(name="sairfila")
    async def sairfila(self, ctx: commands.Context):
        """Remove você da fila de dupla."""
        uid = str(ctx.author.id)
        fila = _load("fila")
        nova = [f for f in fila if f["uid"] != uid]
        if len(nova) == len(fila):
            await ctx.reply("⚠️ Você não está na fila.", delete_after=10)
            return
        _save("fila", nova)
        await ctx.reply("✅ Você saiu da fila.")

    @app_commands.command(name="perfil", description="Veja seu perfil ou o de outro jogador.")
    @app_commands.describe(membro="Jogador (deixe em branco para ver o seu)")
    async def perfil(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        alvo = membro or interaction.user
        uid = str(alvo.id)
        perfis = _load("perfis")
        reputacoes = _load("reputacoes")

        if uid not in perfis:
            await interaction.response.send_message(
                f"⚠️ {'Esse jogador' if membro else 'Você'} ainda não criou um perfil.",
                ephemeral=True,
            )
            return

        p = perfis[uid]
        rep = reputacoes.get(uid, {"total": 0, "count": 0, "toxico": 0, "melhor_parceiro": {}})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        mp_data = rep.get("melhor_parceiro", {})
        melhor = None
        if mp_data:
            melhor_uid = max(mp_data, key=mp_data.get)
            melhor = perfis.get(melhor_uid, {}).get("nick", melhor_uid)

        matches = _load("matches")
        duplas = sum(1 for m in matches if uid in (m["uid_a"], m["uid_b"]) and m.get("avaliado"))

        embed = discord.Embed(title=f"🎮 Perfil — {p['nick']}", color=0xD4A843)
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="🏆 Rank", value=p.get("rank", "Desconhecido"), inline=True)
        embed.add_field(name="🎙️ Microfone", value="Sim ✅" if p.get("microfone") else "Não ❌", inline=True)
        embed.add_field(name="⭐ Avaliação", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.add_field(name="🤝 Duplas encontradas", value=str(duplas), inline=True)
        embed.add_field(name="🏅 Melhor parceiro", value=melhor or "—", inline=True)
        embed.add_field(name="☠️ Reportes tóxico", value=str(rep.get("toxico", 0)), inline=True)

        await interaction.response.send_message(embed=embed)

    @commands.command(name="fila")
    @commands.has_permissions(administrator=True)
    async def ver_fila(self, ctx: commands.Context):
        """[Admin] Lista a fila atual."""
        fila = _load("fila")
        if not fila:
            await ctx.reply("📭 A fila está vazia.")
            return
        linhas = [
            f"**{i+1}.** {f['nick']} — {f['rank']} | {f['modo']} | {f['objetivo']}"
            for i, f in enumerate(fila)
        ]
        embed = discord.Embed(
            title=f"🕐 Fila ({len(fila)} jogadores)",
            description="\n".join(linhas),
            color=0x5865F2,
        )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
