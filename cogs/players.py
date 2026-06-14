"""
cogs/players.py  –  Sistema de Achar Dupla
==========================================
Comandos:
  !setuperfil   → Modal: nick + microfone. Rank puxado via TRN/tracker.
  !setupdupla   → Modal: modo, objetivo, microfone, rank procurado.

Fluxo:
  • Player entra na fila.
  • A cada 30 min o bot pergunta no PV se ainda está procurando.
  • Se não responder em 10 min → removido da fila.
  • Ao fazer match → categoria MATCH-XXXX com chat + voz, DM de convite.
  • Convite tem 2 min para aceitar/recusar.
  • Após partidas → modal de avaliação (tóxico? + estrelas).
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

def _load(name: str) -> dict | list:
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
#  Ranks do Rocket League (ordem crescente)
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

def _ranks_compativeis(rank: str, preferencia: str) -> list[str]:
    """Retorna lista de ranks aceitos com base na preferência."""
    idx = RANK_INDEX.get(rank, 0)
    if preferencia == "mesmo":
        return [rank]
    if preferencia == "±1":
        return [RANKS[i] for i in range(max(0, idx-1), min(len(RANKS), idx+2))]
    return RANKS  # qualquer

# ──────────────────────────────────────────────
#  Helpers de estrelas
# ──────────────────────────────────────────────
def _estrelas(valor: float) -> str:
    cheia, metade = int(valor), (valor % 1 >= 0.5)
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
        mic_raw = self.microfone.value.strip().lower()
        mic = mic_raw in ("sim", "s", "yes", "y")
        nick = self.nick.value.strip()

        # ── Rank: tenta buscar (simulado aqui; integre TRN se quiser) ──
        rank = await self.cog._fetch_rank(nick)

        perfis: dict = _load("perfis")
        uid = str(interaction.user.id)

        reputacoes: dict = _load("reputacoes")
        rep = reputacoes.get(uid, {"total": 0, "count": 0, "toxico": 0})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        perfis[uid] = {
            "nick": nick,
            "microfone": mic,
            "rank": rank,
            "usuario": str(interaction.user),
            "criado_em": int(time.time()),
        }
        _save("perfis", perfis)

        embed = discord.Embed(
            title="✅ Perfil criado!",
            color=0xD4A843,
        )
        embed.add_field(name="🎮 Nick", value=nick, inline=True)
        embed.add_field(name="🏆 Rank", value=rank, inline=True)
        embed.add_field(name="🎙️ Microfone", value="Sim ✅" if mic else "Não ❌", inline=True)
        embed.add_field(name="⭐ Reputação", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Use /perfil para ver seu perfil completo.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        perfis: dict = _load("perfis")

        if uid not in perfis:
            await interaction.response.send_message(
                "⚠️ Você precisa criar seu perfil primeiro com `!setuperfil`.",
                ephemeral=True,
            )
            return

        perfil = perfis[uid]

        # Normaliza campos
        modo_val      = self.modo.value.strip()
        objetivo_val  = self.objetivo.value.strip()
        mic_val       = self.mic_req.value.strip().lower()
        rank_pref_val = self.rank_pref.value.strip().lower()

        mic_obrigatorio = mic_val in ("obrigatório", "obrigatorio", "sim", "s")
        rank_pref_norm  = "mesmo" if "mesmo" in rank_pref_val else ("±1" if "1" in rank_pref_val else "qualquer")

        fila: list = _load("fila")

        # Remove entrada anterior se existir
        fila = [f for f in fila if f["uid"] != uid]

        entrada = {
            "uid": uid,
            "nick": perfil["nick"],
            "rank": perfil["rank"],
            "microfone": perfil["microfone"],
            "modo": modo_val,
            "objetivo": objetivo_val,
            "mic_obrigatorio": mic_obrigatorio,
            "rank_pref": rank_pref_norm,
            "entrou_em": int(time.time()),
            "ultimo_ping": int(time.time()),
        }
        fila.append(entrada)
        _save("fila", fila)

        reputacoes: dict = _load("reputacoes")
        rep = reputacoes.get(uid, {"total": 0, "count": 0, "toxico": 0})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        embed = discord.Embed(
            title="🔍 Procurando dupla…",
            description="Você entrou na fila! Aguarde enquanto buscamos alguém compatível.",
            color=0x5865F2,
        )
        embed.add_field(name="🎮 Modo", value=modo_val, inline=True)
        embed.add_field(name="🎯 Objetivo", value=objetivo_val, inline=True)
        embed.add_field(name="🎙️ Mic req.", value="Obrigatório" if mic_obrigatorio else "Tanto faz", inline=True)
        embed.add_field(name="🏆 Rank procurado", value=rank_pref_norm, inline=True)
        embed.add_field(name="⭐ Sua rep.", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.set_footer(text="A cada 30 min você receberá uma confirmação no PV.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Tenta fazer match imediato
        asyncio.create_task(self.cog._tentar_match(interaction.guild))

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
        self.respostas: dict[str, bool] = {}

    async def _verificar_respostas(self, interaction: discord.Interaction):
        if len(self.respostas) < 2:
            return  # aguarda o outro

        aceitaram = all(self.respostas.values())
        if aceitaram:
            await self.cog._criar_canal_match(interaction.guild, self.match_id, self.uid_a, self.uid_b)
        else:
            # Quem recusou sai; quem aceitou volta pra fila
            for uid, aceitou in self.respostas.items():
                if aceitou:
                    await self.cog._reinserir_fila(uid, interaction.guild)
            await interaction.followup.send(
                "❌ Um dos jogadores recusou. Voltando à fila…", ephemeral=True
            )

        self.stop()

    @discord.ui.button(label="✅ Aceitar", style=discord.ButtonStyle.success, custom_id="convite_aceitar")
    async def aceitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.respostas[str(interaction.user.id)] = True
        await interaction.response.send_message("✅ Você aceitou! Aguardando o outro jogador…", ephemeral=True)
        await self._verificar_respostas(interaction)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger, custom_id="convite_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.respostas[str(interaction.user.id)] = False
        await interaction.response.send_message("❌ Você recusou o match.", ephemeral=True)
        await self._verificar_respostas(interaction)

    async def on_timeout(self):
        # Quem não respondeu sai da fila
        pass

# ──────────────────────────────────────────────
#  View: Avaliação pós-partida
# ──────────────────────────────────────────────
class AvaliacaoModal(discord.ui.Modal):
    def __init__(self, cog: "Players", avaliado_uid: str, avaliado_nick: str):
        super().__init__(title=f"Avaliar {avaliado_nick}")
        self.cog = cog
        self.avaliado_uid = avaliado_uid

        self.toxico = discord.ui.TextInput(
            label="Foi tóxico? (Sim / Não)",
            placeholder="Não",
            max_length=3,
        )
        self.estrelas = discord.ui.TextInput(
            label="Reputação (1 a 5 estrelas)",
            placeholder="5",
            max_length=1,
        )
        self.add_item(self.toxico)
        self.add_item(self.estrelas)

    async def on_submit(self, interaction: discord.Interaction):
        toxico = self.toxico.value.strip().lower() in ("sim", "s", "yes")
        try:
            nota = max(1, min(5, int(self.estrelas.value.strip())))
        except ValueError:
            nota = 5

        reputacoes: dict = _load("reputacoes")
        rep = reputacoes.get(self.avaliado_uid, {"total": 0, "count": 0, "toxico": 0, "melhor_parceiro": {}})
        rep["total"] += nota
        rep["count"] += 1
        if toxico:
            rep["toxico"] += 1

        # Registra melhor parceiro
        avaliador = str(interaction.user.id)
        mp = rep.get("melhor_parceiro", {})
        mp[avaliador] = mp.get(avaliador, 0) + nota
        rep["melhor_parceiro"] = mp

        reputacoes[self.avaliado_uid] = rep
        _save("reputacoes", reputacoes)

        avg = round(rep["total"] / rep["count"], 1)
        await interaction.response.send_message(
            f"✅ Avaliação registrada! {_estrelas(avg)} — Obrigado pelo feedback.",
            ephemeral=True,
        )

# ──────────────────────────────────────────────
#  View: Confirmação de atividade no PV
# ──────────────────────────────────────────────
class AtividadeView(discord.ui.View):
    def __init__(self, cog: "Players", uid: str):
        super().__init__(timeout=600)  # 10 min
        self.cog = cog
        self.uid = uid
        self.respondeu = False

    @discord.ui.button(label="✅ Sim, ainda procuro", style=discord.ButtonStyle.success)
    async def sim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid:
            return
        self.respondeu = True
        fila: list = _load("fila")
        for f in fila:
            if f["uid"] == self.uid:
                f["ultimo_ping"] = int(time.time())
        _save("fila", fila)
        await interaction.response.edit_message(
            content="✅ Ótimo! Continuamos procurando sua dupla.", view=None
        )
        self.stop()

    @discord.ui.button(label="❌ Não, pode me remover", style=discord.ButtonStyle.danger)
    async def nao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid:
            return
        self.respondeu = True
        fila: list = _load("fila")
        fila = [f for f in fila if f["uid"] != self.uid]
        _save("fila", fila)
        await interaction.response.edit_message(
            content="👋 Você foi removido da fila. Use `!setupdupla` quando quiser procurar novamente.",
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        if not self.respondeu:
            fila: list = _load("fila")
            fila = [f for f in fila if f["uid"] != self.uid]
            _save("fila", fila)

# ──────────────────────────────────────────────
#  Cog Principal
# ──────────────────────────────────────────────
class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._matches_pendentes: dict[str, dict] = {}
        self.verificar_atividade.start()
        self.atualizar_ranks.start()

    def cog_unload(self):
        self.verificar_atividade.cancel()
        self.atualizar_ranks.cancel()

    # ── Rank (stub — integre TRN aqui) ──────────
    async def _fetch_rank(self, nick: str) -> str:
        """
        Busca rank do jogador via Tracker Network ou outra API.
        Por enquanto retorna um rank padrão.
        Substitua por chamada HTTP real usando httpx.
        """
        # Exemplo com httpx (descomente e configure sua API KEY):
        # import httpx
        # url = f"https://api.tracker.gg/api/v2/rocket-league/standard/profile/epic/{nick}"
        # headers = {"TRN-Api-Key": os.getenv("TRN_API_KEY", "")}
        # async with httpx.AsyncClient() as client:
        #     r = await client.get(url, headers=headers, timeout=10)
        #     if r.status_code == 200:
        #         data = r.json()
        #         # extrai rank dos dados retornados
        #         ...
        return "Gold II"  # placeholder

    # ── Match ────────────────────────────────────
    async def _tentar_match(self, guild: discord.Guild):
        await asyncio.sleep(1)
        fila: list = _load("fila")
        if len(fila) < 2:
            return

        # Ordena por tempo de entrada (FIFO)
        fila.sort(key=lambda x: x["entrou_em"])

        matched = []
        used = set()

        for i, a in enumerate(fila):
            if a["uid"] in used:
                continue
            for j, b in enumerate(fila):
                if i == j or b["uid"] in used:
                    continue
                if self._sao_compativeis(a, b):
                    matched.append((a, b))
                    used.add(a["uid"])
                    used.add(b["uid"])
                    break

        if not matched:
            return

        # Remove da fila e salva
        novos_uids = used
        fila = [f for f in fila if f["uid"] not in novos_uids]
        _save("fila", fila)

        for a, b in matched:
            match_id = "".join(random.choices(string.digits, k=4))
            await self._enviar_convite(guild, match_id, a, b)

    def _sao_compativeis(self, a: dict, b: dict) -> bool:
        # Modo igual
        if a["modo"].lower() != b["modo"].lower():
            return False
        # Objetivo igual
        if a["objetivo"].lower() != b["objetivo"].lower():
            return False
        # Microfone
        if a["mic_obrigatorio"] and not b["microfone"]:
            return False
        if b["mic_obrigatorio"] and not a["microfone"]:
            return False
        # Rank
        ranks_a = _ranks_compativeis(a["rank"], a["rank_pref"])
        ranks_b = _ranks_compativeis(b["rank"], b["rank_pref"])
        return b["rank"] in ranks_a and a["rank"] in ranks_b

    async def _enviar_convite(self, guild: discord.Guild, match_id: str, a: dict, b: dict):
        reputacoes: dict = _load("reputacoes")

        def rep_str(uid):
            rep = reputacoes.get(uid, {"total": 0, "count": 0})
            avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0
            return f"{_estrelas(avg)} ({avg}/5.0)"

        view = ConviteView(self, match_id, a["uid"], b["uid"])
        self._matches_pendentes[match_id] = {"a": a, "b": b, "view": view}

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

        # Timeout automático
        await asyncio.sleep(120)
        if match_id in self._matches_pendentes:
            # Ninguém respondeu — volta para fila
            del self._matches_pendentes[match_id]

    async def _reinserir_fila(self, uid: str, guild: discord.Guild):
        perfis: dict = _load("perfis")
        if uid not in perfis:
            return
        # Reinsere com dados anteriores (precisa de contexto salvo, simplifique se quiser)
        # Aqui apenas notifica o jogador
        try:
            user = await self.bot.fetch_user(int(uid))
            await user.send("🔄 Você foi reinserido na fila. Procurando nova dupla…")
        except Exception:
            pass

    async def _criar_canal_match(self, guild: discord.Guild, match_id: str, uid_a: str, uid_b: str):
        perfis: dict = _load("perfis")
        pa = perfis.get(uid_a, {})
        pb = perfis.get(uid_b, {})

        try:
            member_a = guild.get_member(int(uid_a)) or await guild.fetch_member(int(uid_a))
            member_b = guild.get_member(int(uid_b)) or await guild.fetch_member(int(uid_b))
        except Exception as e:
            print(f"[PLAYERS] Erro ao buscar membros: {e}")
            return

        # Cria categoria
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

        reputacoes: dict = _load("reputacoes")
        def rep_avg(uid):
            rep = reputacoes.get(uid, {"total": 0, "count": 0})
            return round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        embed = discord.Embed(
            title="✅ Dupla Encontrada!",
            color=0xD4A843,
        )
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
        fila_entry = _load("fila")
        # pega objetivo da última entrada (pode já ter saído da fila)
        entrada_a = next((f for f in _load("fila") if f["uid"] == uid_a), None)
        if entrada_a:
            embed.add_field(name="🎯 Objetivo", value=entrada_a.get("objetivo", "—"), inline=True)

        embed.set_footer(text=f"Canais disponíveis por 3 horas • MATCH-{match_id}")

        msg = await chat.send(
            content=f"{member_a.mention} {member_b.mention}",
            embed=embed,
        )

        # Salva match para avaliação posterior
        matches: list = _load("matches")
        matches.append({
            "match_id": match_id,
            "uid_a": uid_a,
            "uid_b": uid_b,
            "criado_em": int(time.time()),
            "categoria_id": categoria.id,
            "avaliado": False,
        })
        _save("matches", matches)

        # Agenda avaliação após 1 hora (ajuste conforme necessidade)
        asyncio.create_task(self._agendar_avaliacao(match_id, uid_a, uid_b, pa, pb, 3600))

    async def _agendar_avaliacao(self, match_id, uid_a, uid_b, pa, pb, delay_s):
        await asyncio.sleep(delay_s)
        await self._pedir_avaliacao(uid_a, uid_b, pb.get("nick", uid_b))
        await self._pedir_avaliacao(uid_b, uid_a, pa.get("nick", uid_a))

        # Remove categoria
        matches: list = _load("matches")
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
            modal = AvaliacaoModal(self, avaliado_uid, avaliado_nick)

            class AvaliacaoView(discord.ui.View):
                def __init__(self_v):
                    super().__init__(timeout=3600)

                @discord.ui.button(label=f"⭐ Avaliar {avaliado_nick}", style=discord.ButtonStyle.primary)
                async def abrir(self_v, interaction: discord.Interaction, btn):
                    await interaction.response.send_modal(modal)
                    self_v.stop()

            await user.send(
                f"🎮 Sua partida com **{avaliado_nick}** terminou! Como foi jogar com ele?",
                view=AvaliacaoView(),
            )
        except Exception as e:
            print(f"[PLAYERS] Erro ao pedir avaliação: {e}")

    # ── Task: Verificar atividade a cada 30 min ──
    @tasks.loop(minutes=30)
    async def verificar_atividade(self):
        fila: list = _load("fila")
        agora = int(time.time())
        for entrada in list(fila):
            uid = entrada["uid"]
            try:
                user = await self.bot.fetch_user(int(uid))
                view = AtividadeView(self, uid)
                await user.send(
                    "⏰ Você ainda está procurando dupla?\n"
                    "Se não responder em 10 minutos, será removido da fila.",
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
        perfis: dict = _load("perfis")
        for uid, perfil in perfis.items():
            novo_rank = await self._fetch_rank(perfil.get("nick", ""))
            perfil["rank"] = novo_rank
        _save("perfis", perfis)
        print("[PLAYERS] ✅ Ranks atualizados.")

    @atualizar_ranks.before_loop
    async def before_ranks(self):
        await self.bot.wait_until_ready()

    # ── Comandos ─────────────────────────────────
    @commands.command(name="setuperfil")
    async def setuperfil(self, ctx: commands.Context):
        """Cria ou atualiza seu perfil de jogador."""
        await ctx.send_modal(PerfilModal(self))  # type: ignore[attr-defined]

    @commands.command(name="setupdupla")
    async def setupdupla(self, ctx: commands.Context):
        """Entra na fila para achar dupla."""
        await ctx.send_modal(DuplaModal(self))  # type: ignore[attr-defined]

    @app_commands.command(name="perfil", description="Veja seu perfil ou o de outro jogador.")
    @app_commands.describe(membro="Jogador (deixe em branco para ver o seu)")
    async def perfil(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        alvo = membro or interaction.user
        uid = str(alvo.id)
        perfis: dict = _load("perfis")
        reputacoes: dict = _load("reputacoes")

        if uid not in perfis:
            await interaction.response.send_message(
                f"⚠️ {'Esse jogador' if membro else 'Você'} ainda não criou um perfil.",
                ephemeral=True,
            )
            return

        p = perfis[uid]
        rep = reputacoes.get(uid, {"total": 0, "count": 0, "toxico": 0, "melhor_parceiro": {}})
        avg = round(rep["total"] / rep["count"], 1) if rep["count"] else 5.0

        # Melhor parceiro
        mp_data = rep.get("melhor_parceiro", {})
        melhor = None
        if mp_data:
            melhor_uid = max(mp_data, key=mp_data.get)
            mp_perfil = perfis.get(melhor_uid, {})
            melhor = mp_perfil.get("nick", melhor_uid)

        # Estatísticas de dupla
        matches: list = _load("matches")
        duplas = sum(1 for m in matches if uid in (m["uid_a"], m["uid_b"]) and m.get("avaliado"))

        embed = discord.Embed(
            title=f"🎮 Perfil — {p['nick']}",
            color=0xD4A843,
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="🏆 Rank", value=p.get("rank", "Desconhecido"), inline=True)
        embed.add_field(name="🎙️ Microfone", value="Sim ✅" if p.get("microfone") else "Não ❌", inline=True)
        embed.add_field(name="⭐ Avaliação", value=f"{_estrelas(avg)} ({avg}/5.0)", inline=True)
        embed.add_field(name="🤝 Duplas encontradas", value=str(duplas), inline=True)
        embed.add_field(name="🏅 Melhor parceiro", value=melhor or "—", inline=True)
        embed.add_field(name="☠️ Reportes de tóxico", value=str(rep.get("toxico", 0)), inline=True)

        await interaction.response.send_message(embed=embed)

    @commands.command(name="sairfila")
    async def sairfila(self, ctx: commands.Context):
        """Remove você da fila de dupla."""
        uid = str(ctx.author.id)
        fila: list = _load("fila")
        nova_fila = [f for f in fila if f["uid"] != uid]
        if len(nova_fila) == len(fila):
            await ctx.reply("⚠️ Você não está na fila.", delete_after=10)
            return
        _save("fila", nova_fila)
        await ctx.reply("✅ Você saiu da fila.")

    @commands.command(name="fila")
    @commands.has_permissions(administrator=True)
    async def ver_fila(self, ctx: commands.Context):
        """[Admin] Lista a fila atual."""
        fila: list = _load("fila")
        if not fila:
            await ctx.reply("📭 A fila está vazia.")
            return
        linhas = [f"**{i+1}.** {f['nick']} — {f['rank']} | {f['modo']} | {f['objetivo']}" for i, f in enumerate(fila)]
        embed = discord.Embed(title=f"🕐 Fila ({len(fila)} jogadores)", description="\n".join(linhas), color=0x5865F2)
        await ctx.reply(embed=embed)


# ──────────────────────────────────────────────
#  Monkey-patch: prefix commands não suportam send_modal nativamente
#  Precisamos de um workaround via slash ou resposta de interação.
#  Aqui usamos slash commands adicionais para !setuperfil e !setupdupla.
# ──────────────────────────────────────────────
async def setup(bot: commands.Bot):
    cog = Players(bot)
    await bot.add_cog(cog)

    # Registra slash equivalentes para os modais
    @bot.tree.command(name="setuperfil", description="Cria ou atualiza seu perfil de jogador.")
    async def _slash_setuperfil(interaction: discord.Interaction):
        await interaction.response.send_modal(PerfilModal(cog))

    @bot.tree.command(name="setupdupla", description="Entra na fila para achar dupla.")
    async def _slash_setupdupla(interaction: discord.Interaction):
        await interaction.response.send_modal(DuplaModal(cog))
