# Relatório de Auditoria — Bot Discord (Sistema de Moderação)

**Escopo analisado:** `main.py`, `console.py`, `welcome.py` (raiz) e os 29 cogs em `cogs/`
(~9.150 linhas de código).

Este relatório documenta todos os problemas encontrados, o impacto de cada um e a
correção aplicada. Nenhuma funcionalidade foi removida — todas as correções preservam
o comportamento existente e a compatibilidade com o resto do projeto.

---

## 🔴 Problemas críticos (corrigidos)

### 1. Risco de corrupção/perda de dados em TODA a persistência JSON
**Onde:** `cogs/backup.py`, `cogs/demote.py`, `cogs/campeonato.py`, `cogs/convites.py`,
`cogs/atividade.py` (e, de forma redundante, `cogs/mod_utils.py`, que já fazia certo).

**Problema:** cada um desses arquivos tinha sua própria cópia de "ler/salvar JSON", e
a maioria escrevia direto em cima do arquivo original:
```python
with open(path, "w", encoding="utf-8") as f:
    json.dump(dados, f, ...)
```
Se o processo do bot morrer no meio dessa escrita — `kill -9`, falta de energia, OOM
killer, crash do host, `pkill` mal feito, etc. — o arquivo fica truncado/corrompido, e
todos os dados daquele arquivo (whitelist, resultados de amistosos, perfis, treinos,
campeonatos, convites, atividade) são perdidos. Na próxima leitura, `json.load()`
lança `JSONDecodeError` e (em vários pontos) isso não era tratado, ou era tratado
devolvendo um dicionário vazio silenciosamente — ou seja, dado real apagado sem
nenhum aviso.

**Impacto:** perda de dados de produção (posso perder toda a whitelist aprovada,
histórico de resultados, etc.) sem qualquer log ou possibilidade de recuperação.

**Correção:** criado um módulo compartilhado `cogs/json_store.py` com duas funções:
- `salvar_json(path, dados)` — escreve num arquivo temporário (`arquivo.tmp<pid>`) e
  só troca pelo definitivo com `os.replace()`, que é **atômico** no sistema
  operacional: ou o arquivo final fica 100% com os dados antigos, ou 100% com os
  novos, nunca "pela metade".
- `ler_json(path, padrao)` — se o JSON estiver corrompido, faz **backup do arquivo
  corrompido** (`arquivo.json.corrompido_<timestamp>`) em vez de descartá-lo, loga um
  aviso claro, e só então devolve o valor padrão — o bot continua funcionando e nada
  se perde silenciosamente.

Todos os 5 módulos citados foram migrados para usar esse helper único (mantendo as
mesmas assinaturas de função, então nenhum outro arquivo que os importa precisou
mudar). Isso também elimina duplicação de código: a mesma lógica de I/O estava
implementada 6 vezes de formas ligeiramente diferentes.

---

### 2. Falha de segurança: escrita de arquivo com nome controlado pelo usuário (path traversal)
**Onde:** `cogs/resultados.py`, comando `/resultado`.

**Problema:**
```python
nome_arquivo = f"transcricao-amistoso-{adversario.lower().replace(' ', '-')}.txt"
with open(nome_arquivo, "w", encoding="utf-8") as f:
    f.write(transcricao_texto)
```
`adversario` é um campo de **texto livre** do slash command (`adversario: str`, sem
validação/regex/choices). O único tratamento era trocar espaço por hífen. Alguém
digitando algo como `../../main` como nome do adversário faria o bot escrever
(sobrescrever!) um arquivo fora da pasta esperada, dentro do próprio diretório do
projeto — incluindo, em tese, `main.py`, `requirements.txt` ou qualquer outro arquivo
que o processo tenha permissão de escrita. Isso é uma escrita arbitrária de arquivo
(path traversal). Mesmo sendo um comando restrito à staff, um erro de digitação ou
uma conta de staff comprometida vira uma sobrescrita perigosa de arquivos do bot.

**Impacto:** potencial sobrescrita de código-fonte do próprio bot → o bot passaria a
executar o conteúdo sobrescrito no próximo restart (risco de execução de código),
além de simplesmente corromper arquivos essenciais do projeto.

**Correção:** criada `_nome_arquivo_seguro()`, que:
- Remove qualquer caractere que não seja letra/número/hífen/underscore (`re.sub`).
- Limita o tamanho do "slug" a 60 caracteres.
- Acrescenta um sufixo aleatório (`uuid4`) para evitar colisão entre amistosos com
  nomes de adversário parecidos.
- Sempre grava dentro de `data/transcricoes/` (pasta dedicada, nunca a raiz do
  projeto).

De quebra, também corrigi o nome do arquivo mostrado no Discord (antes ele mandava o
caminho completo do servidor, tipo `data/transcricoes/transcricao-...txt`, como nome
visível do anexo — agora usa só o nome do arquivo, com `os.path.basename`).

---

### 3. `on_ready` re-sincronizando slash commands a cada reconexão
**Onde:** `main.py`.

**Problema:** `on_ready` pode disparar mais de uma vez no mesmo processo (o
discord.py chama de novo sempre que o bot perde e recupera a conexão via
RESUME/reconnect — não é só na inicialização). O código antigo rodava
`bot.tree.sync()` (+ sync de guild, se configurado) toda vez que isso acontecia.

**Impacto:** em uma conexão instável, isso pode gerar vários `sync()` em sequência
rápida, esbarrando em **rate limit** da API do Discord (a Discord aplica rate limit
agressivo em sync de comandos), deixando os slash commands temporariamente fora do ar
ou o bot recebendo erros 429 repetidos.

**Correção:** adicionada uma flag de módulo (`_pronto_uma_vez`) que garante que a
sincronização só roda na primeira vez que `on_ready` dispara nesse processo.
`change_presence` continua rodando em toda reconexão (é leve e correto reafirmar o
status), agora protegido por `try/except discord.HTTPException` também.

---

## 🟠 Problemas de desempenho / travamento (corrigidos)

### 4. Geração de gráfico (matplotlib) bloqueando o event loop inteiro
**Onde:** `cogs/grafico_jogadores.py`.

**Problema:** `self._gerar_grafico(...)` — que cria `fig, subplots`, desenha barra +
pizza e faz `fig.savefig(..., dpi=150)` — é uma função **síncrona e pesada de CPU**,
chamada diretamente dentro de uma coroutine (`_editar_ou_criar`), sem
`asyncio.to_thread`. Isso roda no event loop principal do bot.

**Impacto:** enquanto o gráfico está sendo renderizado (a cada 15 minutos, e também
sob demanda via `!atualizargrafico`), **o bot inteiro trava** — nenhum outro comando,
em nenhum servidor, é processado até o `savefig` terminar. Em servidores com muitos
membros (o cálculo de `_dados_semana` já itera todos os membros), isso pode significar
travamentos perceptíveis periódicos.

**Correção:** a chamada agora roda em uma thread separada:
```python
buffer = await asyncio.to_thread(self._gerar_grafico, total, ativos, guild.name)
```
O event loop fica livre para continuar processando outros comandos/eventos enquanto o
matplotlib desenha em segundo plano.

---

### 5. Loops de expiração automática podem parar de vez após um único erro
**Onde:** `cogs/moderation.py` (`checar_temporarias` — expira tempbans/timeouts) e
`cogs/demote.py` (`checar_expiracoes` — expulsão automática após quarentena).

**Problema:** um `@tasks.loop` do discord.py, se a coroutine lançar uma exceção não
tratada, **para de rodar para sempre** (não tenta de novo no próximo ciclo) — a menos
que você trate o erro dentro da própria função. Nos dois loops citados, um único
registro com dado malformado (ex: `expira_em` ausente ou em formato inválido — comum
em `demote.py`, que lida com registros "legado") derrubava o loop inteiro.

**Impacto:** consequência silenciosa e grave — tempbans param de expirar sozinhos
(usuário fica banido além do tempo definido, até alguém notar e reiniciar o bot) e a
expulsão automática por quarentena para de funcionar para todo mundo, não só para o
registro problemático.

**Correção:** isolei o processamento por servidor/registro em blocos `try/except`
próprios, logando o erro específico e continuando para o próximo item/ciclo, em vez
de deixar uma exceção arbitrária matar a tarefa inteira. O mesmo tratamento foi
aplicado ao `backup_loop` (item 6 abaixo).

---

### 6. Backup automático podia parar de vez após uma falha pontual
**Onde:** `cogs/backup.py`.

**Problema:** mesmo motivo do item 5 — o corpo do `@tasks.loop(hours=6)` não tinha
tratamento de exceção, e a limpeza de backups antigos (`shutil.rmtree` sobre
`os.listdir("data/backups")`) assumia que **tudo** dentro da pasta era um diretório de
backup válido; um arquivo perdido ali (ex: um `.DS_Store`, ou um `.tmp` de uma escrita
interrompida) faria `shutil.rmtree` lançar `NotADirectoryError` e parar os backups
automáticos permanentemente.

**Correção:**
- Todo o corpo do loop agora está dentro de um `try/except`, então uma falha em um
  ciclo não impede os próximos backups (a cada 6h).
- A limpeza de backups antigos agora só considera entradas que são diretórios de
  verdade (`os.path.isdir`) e trata falha de remoção individual sem abortar o resto.

---

## 🟡 Melhorias de robustez / UX (corrigidas)

### 7. Botões de confirmação podiam mostrar "A interação falhou" mesmo funcionando
**Onde:** `cogs/mod_utils.py`, `ConfirmarView` (usada em `/ban`, `/kick`, `/tempban`,
`/softban`, `/clear` grande, `/canal deletar`, etc.).

**Problema:** os botões "Confirmar"/"Cancelar" nunca chamavam
`interaction.response...` — a interação do clique só era "respondida" indiretamente,
bem depois, via `interaction.followup.send()`. O Discord exige uma resposta em até 3
segundos para não marcar a interação como falha no cliente do usuário. Como a ação de
moderação real (ex: `guild.ban(...)`) acontece **entre** o clique e essa resposta
tardia, em caso de uma chamada mais lenta à API do Discord o moderador podia ver "Esta
interação falhou" no próprio clique, mesmo a ação tendo sido executada com sucesso —
uma UX confusa e potencialmente levando a ações duplicadas por engano.

**Correção:** os botões agora chamam `await interaction.response.defer()`
imediatamente ao serem clicados, confirmando (ack) a interação na hora. O restante do
fluxo (`followup.send` para a resposta final) continua funcionando exatamente como
antes, já que o código já checava `interaction.response.is_done()`.

### 8. `import asyncio` fora do topo do arquivo
**Onde:** `main.py`.

**Problema:** `import asyncio` estava dentro do bloco `if __name__ == "__main__":`,
no fim do arquivo, mas era usado dentro de `main()` (`asyncio.create_task(...)`),
definida bem acima. Funcionava por acaso (o nome só precisa existir no momento em que
`main()` é *chamada*, não quando é *definida*), mas é uma armadilha: se alguém importar
`main.py` como módulo (testes, outro script, etc.) sem passar pelo bloco
`__main__`, `asyncio` não existiria e o bot quebraria com um `NameError` confuso.

**Correção:** `import asyncio` movido para o topo do arquivo, junto dos outros
imports — comportamento idêntico, só deixa de depender de uma coincidência de ordem
de execução.

### 9. Token ausente gerava erro confuso lá no fundo do discord.py
**Onde:** `main.py`.

**Problema:** se `DISCORD_TOKEN` não estivesse definido no `.env` (erro humano comum,
principalmente em primeira instalação), `TOKEN` seria `None` e só se descobriria isso
quando `bot.start(None)` explodisse com uma exceção genérica lá dentro da biblioteca,
sem indicar a causa real de forma clara.

**Correção:** adicionada uma checagem explícita no início de `main()` que interrompe a
execução com uma mensagem direta explicando exatamente o que fazer (criar o `.env` com
`DISCORD_TOKEN=...`).

### 10. Arquivo duplicado e desatualizado na raiz do projeto (risco de erro humano)
**Onde:** `welcome.py` (raiz do projeto) vs. `cogs/welcome.py`.

**Problema:** existia um `welcome.py` solto na raiz do projeto que era uma cópia
**antiga** de `cogs/welcome.py` — sem o menu de seleção de rank que a versão atual
tem. Ele nunca é carregado pelo bot (a lista `COGS` em `main.py` só referencia
`"cogs.welcome"`), mas continuava lá, sujeito a alguém abrir/editar esse arquivo
pensando que está mexendo no cog de boas-vindas de verdade — e não entender por que
"nada muda" no bot depois.

**Correção:** renomeado para `welcome.py.OBSOLETO`, com um comentário no topo
explicando a situação. Nada foi apagado (o conteúdo original continua no arquivo,
preservado por segurança), mas ele deixa de se parecer com um `.py` ativo e
confundir quem mexer no projeto depois. O cog que realmente roda é `cogs/welcome.py`
— esse não foi alterado.

---

## 🔵 Pontos observados, mas **não** alterados (avaliados como comportamento
correto ou fora de escopo)

Registrado aqui para transparência da auditoria — foram checados e não configuram bug:

- **Hierarquia de cargos em moderação (`cogs/mod_utils.py::pode_moderar`)**: já
  bloqueia auto-moderação, moderar o dono do servidor, e respeita corretamente a
  posição de cargos (`top_role`) tanto do moderador quanto do bot. Correto.
- **AutoMod (`cogs/automod.py`)**: já imuniza administradores, `manage_guild` e
  cargos configurados como staff/imunes antes de aplicar qualquer ação. Correto.
- **Anti-raid (`cogs/antiraid.py`)**: detecção por janela deslizante de entradas +
  heurística de "conta nova" está coerente; modo de emergência é manual e documentado
  no próprio embed de aviso.
- **`/clear`, `/ban`, `/kick`, `/tempban`, `/softban`, exclusão de canal**: todos já
  pedem confirmação (configurável por servidor via `exigir_confirmacao`) e todos
  tratam `discord.Forbidden` corretamente.
- **Limite de caracteres de embed** (`cogs/logs.py`): o conteúdo de mensagens
  logadas já é truncado para 1024 caracteres antes de virar `field` de embed
  (limite da API do Discord) — nenhum ajuste necessário.
- **Comando `!sexbabybye` (expulsão em massa) em `cogs/demote.py`**: já é
  restrito a uma lista fixa de IDs autorizados, exige uma palavra de confirmação
  exata, mostra prévia de quem será afetado, pede confirmação por reação com timeout,
  e aplica um `asyncio.sleep(1.0)` entre expulsões para não estourar rate limit. Bem
  implementado.
- **Chamadas HTTP externas** (`cogs/tiktok.py`, `cogs/tracker.py`): usam `httpx`
  com `async with` (fecha a conexão corretamente) e timeout explícito — sem
  vazamento de conexões.

---

## 📋 Resumo das alterações por arquivo

| Arquivo | O que mudou |
|---|---|
| `cogs/json_store.py` | **Novo.** Helper compartilhado de leitura/escrita JSON atômica e resiliente a corrupção. |
| `cogs/backup.py` | Usa `json_store`; loop de backup protegido contra falhas; limpeza de backups antigos mais segura. |
| `cogs/demote.py` | Usa `json_store`; loop de expiração de quarentena isolado por registro contra falhas. |
| `cogs/campeonato.py` | Usa `json_store`. |
| `cogs/convites.py` | Usa `json_store`. |
| `cogs/atividade.py` | Usa `json_store` (config e dados). |
| `cogs/mod_utils.py` | Passa a delegar ao `json_store` (já era atômico, agora sem duplicar a lógica); `ConfirmarView` faz `defer()` imediato nos botões. |
| `cogs/moderation.py` | Loop `checar_temporarias` isolado por servidor contra falhas. |
| `cogs/grafico_jogadores.py` | Geração do gráfico movida para thread separada (`asyncio.to_thread`) — não trava mais o bot. |
| `cogs/resultados.py` | Corrigida falha de path traversal na geração do arquivo de transcrição; nome de arquivo mostrado ao usuário corrigido. |
| `main.py` | Import de `asyncio` no topo; sync de slash commands só na primeira vez; checagem de `DISCORD_TOKEN` ausente. |
| `welcome.py` → `welcome.py.OBSOLETO` | Arquivo duplicado/morto sinalizado para evitar edição por engano. |

**Nenhuma funcionalidade foi removida.** Todas as assinaturas de função usadas por
outros módulos (`ler`, `salvar`, `ler_campeonatos`, `salvar_campeonatos`, `_ler`,
`_salvar`, `ler_dados`, `salvar_dados`, `_ler_raw`, `_salvar_raw`) permanecem
idênticas — só a implementação interna ficou mais segura.

---

## ✅ Recomendações para o futuro (não implementadas nesta rodada, por estarem fora
do escopo de "correção de bug" e exigirem decisão do dono do projeto)

1. **Testes automatizados**: não há nenhum teste no projeto. Mesmo alguns testes
   simples para `cogs/json_store.py` e `cogs/mod_utils.py` (as partes mais
   "lógicas" e reutilizadas) ajudariam a prevenir regressões futuras.
2. **Variáveis de configuração hardcoded**: vários cogs (`demote.py`, `atividade.py`,
   `campeonato.py`, `resultados.py` etc.) têm IDs de canal/cargo/usuário fixos no
   código-fonte. Funciona, mas migrar para `.env` ou um arquivo `config.json` deixaria
   mais fácil reaproveitar o bot em outro servidor sem editar código.
3. **Atualizar `discord.py`**: o `requirements.txt` fixa `discord.py==2.3.2`; versões
   mais novas (2.4+) trazem correções de bugs da própria biblioteca e substituem
   parâmetros como `delete_message_days` (usado em `/ban`) pelo mais novo
   `delete_message_seconds`, que tem granularidade melhor.
4. **Rate limit interno em comandos pesados**: comandos como `/resultado` (gera
   transcrição do canal inteiro) ou o gráfico de novatos não têm cooldown próprio —
   hoje isso é mitigado pelas permissões exigidas, mas um `@commands.cooldown` extra
   custaria pouco e evitaria abuso acidental (várias pessoas de staff rodando o mesmo
   comando pesado ao mesmo tempo).
