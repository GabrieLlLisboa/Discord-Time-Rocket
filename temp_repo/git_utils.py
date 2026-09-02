import subprocess


def _rodar(args: list[str], cwd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _saida(resultado: subprocess.CompletedProcess) -> str:
    return ((resultado.stdout or "") + (resultado.stderr or "")).strip()


# frases que o git usa quando o pull falha porque tem coisa não commitada
# no working tree atrapalhando o merge — nesses casos dá pra recuperar
# sozinho com um "git reset --hard" pro estado remoto
_SINAIS_DE_CONFLITO_LOCAL = (
    "would be overwritten by merge",
    "please commit your changes or stash them",
    "cannot fast-forward your working tree",
    "your local changes to the following files",
)


def pull_com_recuperacao_sync(cwd: str, timeout: int = 60) -> tuple[bool, str, bool]:
    """
    Roda 'git pull'. Se falhar por causa de mudanças locais no working tree
    (o cenário mais comum quando dois updates rodam meio que ao mesmo tempo,
    ou alguém mexeu num arquivo direto no servidor), tenta se recuperar
    sozinho com 'git fetch' + 'git reset --hard @{u}' (reseta pro estado
    exato da branch remota) e tenta o pull de novo.

    Retorna (sucesso, saida_completa_pra_log, recuperou_sozinho).
    """
    pull = _rodar(["pull"], cwd=cwd, timeout=timeout)
    saida = _saida(pull)

    if pull.returncode == 0:
        return True, saida, False

    saida_lower = saida.lower()
    eh_conflito_local = any(sinal in saida_lower for sinal in _SINAIS_DE_CONFLITO_LOCAL)

    if not eh_conflito_local:

        return False, saida, False

    fetch = _rodar(["fetch", "--quiet"], cwd=cwd, timeout=timeout)
    if fetch.returncode != 0:
        saida_total = saida + "\n\n[tentativa de recuperação] git fetch falhou:\n" + _saida(fetch)
        return False, saida_total, False

    reset = _rodar(["reset", "--hard", "@{u}"], cwd=cwd, timeout=timeout)
    saida_reset = _saida(reset)

    if reset.returncode != 0:
        saida_total = saida + "\n\n[tentativa de recuperação] git reset --hard falhou:\n" + saida_reset
        return False, saida_total, False

    saida_total = (
        saida
        + "\n\n[recuperação automática] o pull falhou por causa de mudanças locais no "
        + "working tree, então rodei 'git reset --hard' pra alinhar com o remoto:\n"
        + saida_reset
    )
    return True, saida_total, True
