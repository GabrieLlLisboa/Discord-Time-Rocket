# ============================================================
# AUTO GIT - Discord Time Rocket
# Detecta alteracoes, cria o commit e envia pro GitHub,
# mostrando um resumo de cada commit no console.
# ============================================================

$ErrorActionPreference = "Continue"

# Deixa as linhas desenhadas aparecerem certo no console
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# ---------------- CONFIGURACAO ----------------

# Pasta do projeto
$RepoPath = "C:\Users\gabri\Documents\github\Discord Time Rocket"

# Branch e remoto
$Remote = "origin"
$Branch = "main"

# Tempo de espera apos uma alteracao (pra agrupar varios arquivos salvos juntos)
$DelaySeconds = 5

# Quanto tempo ate a versao chegar no site oficial (so informativo)
$DeploySeconds = 30

# (opcional) link do site oficial, aparece no final. Ex: "https://meusite.com"
$SiteOficial = ""

# Quantos arquivos listar no resumo (o resto vira "e mais N arquivos")
$MaxArquivosNaLista = 12

# Extensoes/pastas que nao devem disparar commits
$IgnoredFolders = @(
    ".git",
    ".git_old",
    ".git_backup_temp",
    "temp_repo",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules"
)

# ---------------- VISUAL ----------------

$Barra = ([string][char]0x2501) * 46
$Fina  = ([string][char]0x2500) * 46

$script:ContagemAtiva = $false
$script:DeployAt = $null

function Limpar-Contagem {
    # apaga a linha da contagem regressiva antes de escrever outra coisa
    if ($script:ContagemAtiva) {
        Write-Host ("`r" + (" " * 70) + "`r") -NoNewline
        $script:ContagemAtiva = $false
    }
}

function Write-Campo {
    param([string]$Rotulo, [string]$Valor, $Cor = "White")
    Write-Host ("   " + $Rotulo.PadRight(15)) -NoNewline -ForegroundColor DarkGray
    Write-Host $Valor -ForegroundColor $Cor
}

function Cortar-Texto {
    param([string]$Texto, [int]$Max)
    if ($Texto.Length -le $Max) { return $Texto }
    return "..." + $Texto.Substring($Texto.Length - ($Max - 3))
}

function Get-RepoWebUrl {
    # Transforma a URL do remoto no link do repositorio no navegador
    # (e TIRA usuario/token da URL pra nunca aparecer na tela)
    param([string]$Url)
    if (-not $Url) { return "" }
    $U = $Url.Trim().TrimEnd('/')
    $U = $U -replace '^git@([^:]+):', 'https://$1/'
    $U = $U -replace '^ssh://git@([^/]+)/', 'https://$1/'
    $U = $U -replace '^(https?://)[^/@]+@', '$1'
    $U = $U -replace '\.git$', ''
    return $U.TrimEnd('/')
}

function Get-ResumoCommit {
    # Le o ultimo commit: arquivos, tipo da mudanca e linhas +/-
    $Resumo = @{ Arquivos = @(); Adicionadas = 0; Removidas = 0 }

    $Status = @(git -c core.quotepath=false show --name-status --no-renames --format= HEAD 2>$null)
    $Nums   = @(git -c core.quotepath=false show --numstat --no-renames --format= HEAD 2>$null)

    $Mapa = @{}
    foreach ($Linha in $Nums) {
        if (-not $Linha) { continue }
        $P = $Linha -split "`t", 3
        if ($P.Count -lt 3) { continue }
        $Mapa[$P[2]] = $P
    }

    foreach ($Linha in $Status) {
        if (-not $Linha) { continue }
        $P = $Linha -split "`t", 2
        if ($P.Count -lt 2) { continue }

        $Caminho = $P[1]
        $Add = 0
        $Del = 0
        $Binario = $false

        if ($Mapa.ContainsKey($Caminho)) {
            $N = $Mapa[$Caminho]
            if ($N[0] -eq "-") {
                $Binario = $true
            } else {
                $Add = [int]$N[0]
                $Del = [int]$N[1]
            }
        }

        $Resumo.Arquivos += [pscustomobject]@{
            Tipo    = $P[0].Substring(0, 1)
            Caminho = $Caminho
            Add     = $Add
            Del     = $Del
            Binario = $Binario
        }
        $Resumo.Adicionadas += $Add
        $Resumo.Removidas   += $Del
    }

    return $Resumo
}

function Show-CommitDetectado {
    param([string]$LinkBase)

    $Hora      = Get-Date -Format "HH:mm:ss"
    $HashCurto = (git rev-parse --short HEAD 2>$null) | Select-Object -First 1
    $HashLongo = (git rev-parse HEAD 2>$null) | Select-Object -First 1
    $Autor     = (git log -1 --format=%an HEAD 2>$null) | Select-Object -First 1
    if (-not $Autor) { $Autor = $env:USERNAME }

    $Resumo   = Get-ResumoCommit
    $Arquivos = @($Resumo.Arquivos)
    $Total    = $Arquivos.Count

    Write-Host ""
    Write-Host ("  " + $Barra) -ForegroundColor Cyan
    Write-Host "   UMA COMMIT FOI DETECTADA" -NoNewline -ForegroundColor White
    Write-Host ("".PadLeft(24) + $Hora) -ForegroundColor DarkGray
    Write-Host ("  " + $Barra) -ForegroundColor Cyan
    Write-Host ""

    Write-Campo "Commit" ("$HashCurto  ($Branch)") "Yellow"
    Write-Host ""

    # --- arquivos que mudaram ---
    $Palavra = "arquivos"
    if ($Total -eq 1) { $Palavra = "arquivo" }
    Write-Host ("   Mudou $Total $Palavra") -ForegroundColor White

    $Mostrar = [Math]::Min($Total, $MaxArquivosNaLista)
    for ($i = 0; $i -lt $Mostrar; $i++) {
        $A = $Arquivos[$i]
        $Simbolo = "?"
        $CorArq  = "Gray"
        if ($A.Tipo -eq "A") { $Simbolo = "+"; $CorArq = "Green" }
        elseif ($A.Tipo -eq "M") { $Simbolo = "~"; $CorArq = "Yellow" }
        elseif ($A.Tipo -eq "D") { $Simbolo = "-"; $CorArq = "Red" }

        Write-Host ("     $Simbolo " + (Cortar-Texto $A.Caminho 40).PadRight(40) + " ") -NoNewline -ForegroundColor $CorArq
        if ($A.Binario) {
            Write-Host "(binario)" -ForegroundColor DarkGray
        } else {
            Write-Host ("+" + $A.Add).PadLeft(6) -NoNewline -ForegroundColor Green
            Write-Host " " -NoNewline
            Write-Host ("-" + $A.Del).PadLeft(6) -ForegroundColor Red
        }
    }
    if ($Total -gt $Mostrar) {
        $Resto = $Total - $Mostrar
        Write-Host ("     ... e mais $Resto arquivo(s)") -ForegroundColor DarkGray
    }
    Write-Host ""

    # --- linhas ---
    Write-Host ("   " + "Linhas".PadRight(15)) -NoNewline -ForegroundColor DarkGray
    Write-Host ("+" + $Resumo.Adicionadas + " adicionadas") -NoNewline -ForegroundColor Green
    Write-Host "   " -NoNewline
    Write-Host ("-" + $Resumo.Removidas + " removidas") -ForegroundColor Red

    # --- link no repositorio ---
    if ($LinkBase -and $HashLongo) {
        Write-Campo "Link" ($LinkBase + "/commit/" + $HashLongo) "Cyan"
    }

    # --- autor ---
    Write-Campo "Commitada por" $Autor "White"

    Write-Host ""
    Write-Host ("  " + $Fina) -ForegroundColor DarkGray
}

# ---------------- INICIO ----------------

# Entrar na pasta do projeto
if (-not (Test-Path $RepoPath)) {
    Write-Host "[ERRO] A pasta do projeto nao existe: $RepoPath" -ForegroundColor Red
    Read-Host "Pressione ENTER para sair"
    exit
}
Set-Location $RepoPath

# Verificar se e um repositorio Git
if (-not (Test-Path ".git")) {
    Write-Host "[ERRO] .git nao encontrado!" -ForegroundColor Red
    Write-Host "O script nao pode continuar."
    Read-Host "Pressione ENTER para sair"
    exit
}

# Verificar se o remoto existe
$RemoteUrl = git remote get-url $Remote 2>$null

if (-not $RemoteUrl) {
    Write-Host "[ERRO] O remoto '$Remote' nao foi encontrado!" -ForegroundColor Red
    Read-Host "Pressione ENTER para sair"
    exit
}

$RepoWeb = Get-RepoWebUrl $RemoteUrl

Write-Host ""
Write-Host ("  " + $Barra) -ForegroundColor Cyan
Write-Host "        DISCORD TIME ROCKET  -  AUTO GIT" -ForegroundColor White
Write-Host ("  " + $Barra) -ForegroundColor Cyan
Write-Host ""
Write-Campo "Pasta" $RepoPath "Gray"
Write-Campo "Repositorio" $RepoWeb "Cyan"
Write-Campo "Branch" "$Remote/$Branch" "Yellow"
Write-Host ""
Write-Host "   [OK] Repositorio Git encontrado." -ForegroundColor Green
Write-Host "   Monitorando alteracoes... (CTRL+C para parar)" -ForegroundColor DarkGray
Write-Host ""

# Cria o watcher do Windows
$Watcher = New-Object System.IO.FileSystemWatcher

$Watcher.Path = $RepoPath
$Watcher.IncludeSubdirectories = $true
$Watcher.EnableRaisingEvents = $true

# Tipos de alteracao monitorados
$Watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName `
    -bor [System.IO.NotifyFilters]::LastWrite `
    -bor [System.IO.NotifyFilters]::Size

$LastCommitTime = Get-Date

while ($true) {

    # Verifica se existem alteracoes reais
    $Status = git status --porcelain 2>$null

    if ($Status) {

        $Now = Get-Date

        # Evita fazer varios commits em sequencia
        if (($Now - $LastCommitTime).TotalSeconds -ge $DelaySeconds) {

            Limpar-Contagem
            $script:DeployAt = $null

            Write-Host ""
            Write-Host ("   [" + (Get-Date -Format "HH:mm:ss") + "] Alteracao detectada! Agrupando por ${DelaySeconds}s...") -ForegroundColor Yellow

            # Espera para permitir que varios arquivos sejam salvos juntos
            Start-Sleep -Seconds $DelaySeconds

            # Verifica novamente
            $Status = git status --porcelain 2>$null

            if ($Status) {

                git add -A

                if ($LASTEXITCODE -ne 0) {
                    Write-Host "   [ERRO] Falha no git add." -ForegroundColor Red
                    $LastCommitTime = Get-Date
                    continue
                }

                # Data/hora para o commit
                $Timestamp = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
                $CommitMessage = "Auto commit - $Timestamp"

                $SaidaCommit = git commit -m "$CommitMessage" 2>&1 | ForEach-Object { "$_" }

                if ($LASTEXITCODE -ne 0) {
                    Write-Host "   [AVISO] Nenhum commit criado ou ocorreu um erro." -ForegroundColor Yellow
                    foreach ($L in $SaidaCommit) { Write-Host ("   " + $L) -ForegroundColor DarkGray }
                    $LastCommitTime = Get-Date
                    continue
                }

                # Resumo bonito do commit que acabou de ser criado
                Show-CommitDetectado -LinkBase $RepoWeb

                Write-Host "   Enviando para o GitHub..." -ForegroundColor DarkGray

                $SaidaPush = git push $Remote $Branch 2>&1 | ForEach-Object { "$_" }

                if ($LASTEXITCODE -eq 0) {
                    Write-Host ""
                    Write-Host "   [OK] Enviado para o GitHub!" -ForegroundColor Green
                    Write-Host ("   Em ~" + $DeploySeconds + " segundos ja estara no site oficial") -ForegroundColor Cyan
                    if ($SiteOficial) {
                        Write-Host ("   " + $SiteOficial) -ForegroundColor Cyan
                    }
                    $script:DeployAt = (Get-Date).AddSeconds($DeploySeconds)
                }
                else {
                    Write-Host ""
                    Write-Host "   [ERRO] O git push falhou." -ForegroundColor Red
                    foreach ($L in $SaidaPush) { Write-Host ("   " + $L) -ForegroundColor DarkGray }
                    Write-Host "   Suas alteracoes continuam salvas localmente."
                }

                Write-Host ""

                $LastCommitTime = Get-Date
            }
        }
    }

    # Contagem regressiva ate a versao chegar no site oficial
    if ($script:DeployAt) {
        $Restante = [int][Math]::Ceiling(($script:DeployAt - (Get-Date)).TotalSeconds)
        if ($Restante -gt 0) {
            Write-Host ("`r   Chegando no site oficial em {0,2}s ...   " -f $Restante) -NoNewline -ForegroundColor DarkCyan
            $script:ContagemAtiva = $true
        }
        else {
            Limpar-Contagem
            Write-Host "   [PRONTO] Prazo de ${DeploySeconds}s concluido - ja deve estar no site oficial." -ForegroundColor Green
            Write-Host ""
            $script:DeployAt = $null
        }
    }

    # Pequena pausa para evitar uso desnecessario de CPU
    Start-Sleep -Milliseconds 1000
}
