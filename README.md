# 🤖 Ignition Bot

Bot do Discord da rede Ignition, feito em Python com `discord.py`.

---

## 📁 Estrutura

```
ignition-bot/
├── main.py              ← Arquivo principal (inicia o bot)
├── .env                 ← Token e configurações (NÃO suba no GitHub)
├── requirements.txt     ← Dependências Python
└── cogs/
    ├── welcome.py       ← Boas-vindas ao entrar no servidor
    └── ...              ← Futuras funcionalidades aqui
```

---

## ⚙️ Instalação

### 1. Instale as dependências
```bash
pip install -r requirements.txt
```

### 2. Configure o `.env`
Abra o arquivo `.env` e preencha:
```env
DISCORD_TOKEN=SEU_TOKEN_AQUI
WELCOME_CHANNEL_ID=1514774138516930661
PREFIX=!
```

### 3. Ative os Intents no Discord Developer Portal
Acesse https://discord.com/developers/applications → seu bot → **Bot**:
- ✅ **SERVER MEMBERS INTENT**
- ✅ **MESSAGE CONTENT INTENT**

### 4. Rode o bot
```bash
python main.py
```

---

## ➕ Adicionar novas funcionalidades

1. Crie um novo arquivo em `cogs/`, ex: `cogs/moderation.py`
2. Use a estrutura padrão de Cog (veja `cogs/welcome.py` como exemplo)
3. Adicione o nome do cog na lista `COGS` dentro de `main.py`:
```python
COGS = [
    "cogs.welcome",
    "cogs.moderation",  # ← aqui
]
```

---

## 📦 Funcionalidades

| Arquivo            | Função                            | Status |
|--------------------|-----------------------------------|--------|
| `cogs/welcome.py`  | Embed de boas-vindas ao entrar    | ✅ Ativo |

---

## 🛡️ Sistema de Moderação

Sistema completo de moderação em Slash Commands + painel de botões, com
banco de dados em JSON (pasta `data/`), hierarquia de cargos e logs
configuráveis.

### Arquivos
| Arquivo                 | Função |
|--------------------------|--------|
| `cogs/mod_utils.py`      | Núcleo: banco de dados, hierarquia, embeds, confirmação |
| `cogs/moderation.py`     | Comandos de moderação (warn, ban, kick, timeout, etc.) |
| `cogs/automod.py`        | AutoMod: spam, flood, links, convites, palavrões, CAPS, menções, emojis, phishing |
| `cogs/antiraid.py`       | Anti-Raid: detecção de entradas em massa e modo de emergência |
| `cogs/mod_config.py`     | Painel `/moderacao-config` (canais de log, cargos, toggles) |
| `cogs/mod_setup.py`      | Comando `!setup-moderacao` — painel de botões + modais |

### Primeiros passos
1. **Convide o bot** com o escopo `bot` + `applications.commands` e as permissões:
   `Administrador` (mais simples) **ou**, no mínimo: Banir/Expulsar membros,
   Gerenciar Cargos/Canais/Mensagens/Apelidos, Moderar Membros (timeout).
2. No servidor, rode `/moderacao-config` e defina:
   - Canal de logs de moderação, de AutoMod e de Anti-Raid
   - Cargos de Staff (usados como "imunes" no AutoMod/Anti-Raid e para o painel de botões)
   - Se quer DM automática pro punido e confirmação obrigatória em ações perigosas
3. Rode `!setup-moderacao` no canal onde a staff vai atuar — isso manda o
   **painel de botões** (Advertir, Timeout, Expulsar, Banir, Ban Temporário,
   Desbanir, Softban, Limpar Mensagens, Slowmode, Nick, Trancar/Destrancar).
   Cada botão abre uma janela (modal) pedindo usuário/motivo/duração.
4. Configure o AutoMod com `/automod status`, `/automod ativar`, `/automod acao`,
   `/automod palavra-adicionar`, `/automod whitelist-link`, `/automod limite`.
5. Configure o Anti-Raid com `/antiraid status`, `/antiraid configurar`,
   `/antiraid acao`, `/antiraid emergencia true` (trava entradas na hora).

### Comandos principais
`/warn` `/avisos` `/removeraviso` `/historico` `/timeout` `/untimeout`
`/kick` `/ban` `/tempban` `/unban` `/softban` `/clear` `/slowmode` `/nick`
`/lock` `/unlock` `/cargo adicionar|remover` `/canal criar|deletar|renomear`
`/thread trancar|destrancar|arquivar` `/automod ...` `/antiraid ...`
`/moderacao-config`

### Observações importantes
- **Hierarquia de cargos**: ninguém consegue moderar quem tem cargo igual ou
  maior, nem o dono do servidor; o bot também precisa estar acima do alvo na
  hierarquia.
- **Banco de dados**: tudo fica em `data/mod_config.json`, `data/mod_punicoes.json`,
  `data/mod_automod.json` e `data/mod_antiraid.json` — inclua a pasta `data/`
  no seu backup.
- **Ban temporário/timeout**: um loop interno confere a cada 1 minuto e
  desbane automaticamente quando o prazo expira.
- Um Modal do Discord só aceita campos de texto (não aceita botões dentro
  dele) — por isso o painel do `!setup-moderacao` usa **botões que abrem
  modais**, e não um único modal com tudo dentro.
