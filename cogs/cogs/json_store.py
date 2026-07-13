"""
Módulo: Persistência JSON segura (compartilhada)
Arquivo: cogs/json_store.py

Vários cogs (backup.py, demote.py, campeonato.py, convites.py, atividade.py...)
tinham cada um a sua própria cópia de "ler/salvar JSON", e a maioria delas
escrevia direto em cima do arquivo original (`open(path, "w")`). Isso é
perigoso: se o bot cair, travar ou for morto (kill -9 / falta de energia /
crash do processo) bem no meio da escrita, o arquivo fica truncado/corrompido
e os dados daquele arquivo (ex: whitelist.json, resultados.json,
campeonatos.json) são perdidos.

Esse módulo centraliza a lógica em duas funções simples e seguras:

  ler_json(path, padrao)     -> lê o arquivo (ou devolve o valor padrão)
  salvar_json(path, dados)   -> escreve de forma ATÔMICA (escreve num
                                 arquivo temporário e só troca pelo arquivo
                                 final com os.replace, que é atômico no
                                 sistema operacional). Ou o arquivo fica
                                 100% com os dados antigos, ou 100% com os
                                 dados novos — nunca "pela metade".

Também protege contra JSON corrompido (arquivo ilegível): em vez de o bot
travar com um traceback, o arquivo corrompido é renomeado (guardado como
".corrompido_<timestamp>" pra não perder a evidência) e a função devolve o
valor padrão, deixando o bot continuar funcionando.
"""

from __future__ import annotations

import json
import os
import time


def ler_json(path: str, padrao):
    """
    Lê um arquivo JSON. Se não existir, devolve `padrao` (pode ser um valor
    ou uma função/callable que gera o valor padrão, útil pra listas/dicts
    mutáveis que não devem ser compartilhados entre chamadas).
    Se o arquivo existir mas estiver corrompido, faz backup do arquivo
    corrompido e devolve `padrao` em vez de derrubar o bot.
    """
    valor_padrao = padrao() if callable(padrao) else padrao

    if not os.path.exists(path):
        return valor_padrao

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        backup_path = f"{path}.corrompido_{int(time.time())}"
        try:
            os.replace(path, backup_path)
            print(f"[JSON_STORE] ⚠️ '{path}' estava corrompido ({e}). "
                  f"Guardado como '{backup_path}' e recriado com valor padrão.")
        except OSError as e2:
            print(f"[JSON_STORE] ⚠️ '{path}' estava corrompido ({e}) e não foi "
                  f"possível fazer backup dele ({e2}). Usando valor padrão.")
        return valor_padrao
    except OSError as e:
        print(f"[JSON_STORE] ⚠️ Erro ao ler '{path}': {e}. Usando valor padrão.")
        return valor_padrao


def salvar_json(path: str, dados) -> None:
    """
    Salva `dados` em `path` de forma atômica: escreve tudo num arquivo
    temporário no mesmo diretório e só substitui o arquivo final quando a
    escrita terminou com sucesso (os.replace é atômico). Isso evita que uma
    queda do processo no meio da escrita corrompa ou apague os dados.
    """
    diretorio = os.path.dirname(path)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)

    tmp_path = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())  # garante que foi pro disco antes do replace
        os.replace(tmp_path, path)
    finally:
        # Se algo deu errado antes do os.replace, não deixa lixo pra trás
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
