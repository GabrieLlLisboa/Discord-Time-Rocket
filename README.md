# Bot de Whitelist — Servidor Minecraft

Bot separado, só com a whitelist. Funciona apenas no servidor `1566899003520716960`.

## Como funciona
1. Alguém entra → o bot cria um canal privado só dessa pessoa (categoria "🔒 Whitelist").
2. Ela clica em **Começar** e responde só 2 coisas:
   - **Qual seu nick do Minecraft?** → o apelido dela no Discord é trocado por esse nick
   - **Java ou Bedrock?**
3. A staff recebe o resumo (no canal + no `LOG_CHANNEL_ID`, se configurado) e clica em **Aprovar** ou **Recusar**.
   - Aprovar: tira o cargo "sem acesso", dá o cargo de membro, canal é apagado em 10 min.
   - Recusar: expulsa a pessoa (pede confirmação), canal é apagado em 10 min.

Validação do nick: Java = 3–16 caracteres (letras, números, `_`). Bedrock = até 16 (letras, números, espaço, `.`).

## Montar o servidor: `!setupmine` (só administrador)
Cria 20 cargos (Direção / Equipe / Survival / Extras, com separadores) e 4 categorias com 20 canais
(informações, comunidade, minecraft e voz). Pode rodar de novo: o que já existe é reaproveitado.
- `@everyone` não vê nada. Quem entra só enxerga o canal da própria whitelist.
- Aprovado na whitelist = ganha **🌱・Novato** e passa a ver o servidor.
- Canais de informações são só leitura (só equipe e bots escrevem).
- Equipe que aprova whitelist: Fundador, Diretor, Adm da Tryharders, Adm do Survival, Administrador, Moderador, Ajudante.
- Ao rodar, ele grava os IDs em `data/config.json` (o `.env` com `STAFF_ROLE_ID` etc. vira só reserva).
- Antes de rodar: arraste o cargo do bot pro **topo** da lista de cargos.

## Comandos (staff)
- `!whitelist @membro` — abre a whitelist de alguém que já está no servidor
- `!aprovar-whitelist` / `!reprovar-whitelist` — dentro do canal da whitelist

## Instalar
```
pip install -r requirements.txt
cp .env.example .env      # preencha DISCORD_TOKEN e os IDs
python main.py
```

## No Discord Developer Portal
- Bot → ligar **Server Members Intent** e **Message Content Intent**
- Permissões do bot no servidor: Gerenciar Canais, Gerenciar Cargos, Gerenciar Apelidos,
  Expulsar Membros, Ver Canais, Enviar Mensagens, Incorporar Links, Ler Histórico.
- O cargo do bot precisa estar **acima** do cargo "sem acesso", do cargo de membro e dos membros que ele edita.

## Cargos (opcional, no .env)
`STAFF_ROLE_ID`, `NO_ACCESS_ROLE_ID`, `MEMBER_ROLE_ID`, `LOG_CHANNEL_ID`, `CATEGORY_ID`.
Sem eles o bot funciona igual (só administradores aprovam, sem troca de cargos).
Para a pessoa não ver o servidor antes de ser aprovada, crie um cargo "sem acesso" (ou deixe os canais
visíveis só pro cargo de membro) e coloque os IDs.
