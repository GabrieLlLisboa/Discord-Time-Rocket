# Whitelist do servidor de Minecraft (no mesmo bot)

O MESMO bot (mesmo token) roda nos dois servidores. No servidor de Minecraft
(`1566899003520716960`) só funciona a whitelist nova + o `!setupmine`.
Todas as outras cogs ignoram esse servidor. Nada do Rocket foi alterado.

## Instalar
Extraia este zip POR CIMA da pasta do bot (ele substitui o `main.py`):
- `main.py`              → 3 mudanças (usa `BotIsolado`, carrega as 2 cogs novas, trata comando bloqueado)
- `isolamento_mine.py`   → faz o servidor de Minecraft ficar "invisível" pras outras cogs
- `cogs/mc_whitelist.py` → a whitelist (nick do Minecraft + Java/Bedrock)
- `cogs/mc_setup.py`     → `!setupmine`
- `cogs/mc_config.py`    → IDs gravados pelo setup (`data/mc_config.json`)
Não precisa instalar nada novo.

## Usar
1. Convide o bot no servidor de Minecraft (Gerenciar Canais, Gerenciar Cargos, Gerenciar Apelidos,
   Expulsar Membros). Arraste o cargo do bot pro TOPO da lista de cargos.
2. No servidor de Minecraft, um administrador digita `!setupmine`.
   Cria 21 cargos (incluindo **🔒・Sem Whitelist**), 4 categorias e 20 canais. Pode rodar de novo sem duplicar.
3. Pronto: quem entra ganha **🔒・Sem Whitelist** (não vê canal nenhum), faz a whitelist no canal
   privado e, ao ser aprovado, troca por **🌱・Novato**.

## Comandos (só no servidor de Minecraft)
- `!setupmine` — monta cargos e canais (administrador)
- `!mcwhitelist @membro` — abre a whitelist de alguém que já está no servidor (staff)
- `!mcaprovar` / `!mcrecusar` — dentro do canal da whitelist (staff)
Os nomes são diferentes dos do Rocket (`!whitelist`, `!aprovar-whitelist`...) pra não colidir.

## .env (tudo opcional)
`MC_GUILD_ID` (padrão 1566899003520716960), `MC_LOG_CHANNEL_ID` (cópia das whitelists pra staff),
`MC_CATEGORY_ID`. O `GUILD_ID` do .env continua sendo o do Rocket.
