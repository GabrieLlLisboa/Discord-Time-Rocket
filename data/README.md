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
