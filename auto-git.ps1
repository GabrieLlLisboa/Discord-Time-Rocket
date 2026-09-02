```powershell
# ============================================================
# AUTO GIT - Discord Time Rocket
# Detecta alterações e envia automaticamente para o GitHub
# ============================================================

$ErrorActionPreference = "Continue"

# Pasta do projeto
$RepoPath = "C:\Users\gabri\Documents\github\Discord Time Rocket"

# Branch e remoto
$Remote = "origin"
$Branch = "main"

# Tempo de espera após uma alteração
$DelaySeconds = 5

Write-Host ""
Write-Host "============================================" 
Write-Host "       DISCORD TIME ROCKET - AUTO GIT"
Write-Host "============================================"
Write-Host ""
Write-Host "Repositorio: $RepoPath"
Write-Host "Remoto:      $Remote"
Write-Host "Branch:      $Branch"
Write-Host ""
Write-Host "Monitorando alteracoes..."
Write-Host "Pressione CTRL+C para parar."
Write-Host ""

# Entrar na pasta do projeto
Set-Location $RepoPath

# Verificar se é um repositorio Git
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

Write-Host "[OK] Repositorio Git encontrado."
Write-Host "[OK] Remoto: $RemoteUrl"
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

$LastCommitTime = Get-Date

while ($true) {

    # Verifica se existem alteracoes reais
    $Status = git status --porcelain 2>$null

    if ($Status) {

        $Now = Get-Date

        # Evita fazer vários commits em sequência
        if (($Now - $LastCommitTime).TotalSeconds -ge $DelaySeconds) {

            Write-Host ""
            Write-Host "--------------------------------------------"
            Write-Host "Alteracao detectada!"
            Write-Host "--------------------------------------------"

            # Espera para permitir que varios arquivos sejam salvos juntos
            Start-Sleep -Seconds $DelaySeconds

            # Verifica novamente
            $Status = git status --porcelain 2>$null

            if ($Status) {

                Write-Host "[1/4] Adicionando arquivos..."

                git add -A

                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[ERRO] Falha no git add." -ForegroundColor Red
                    continue
                }

                # Data/hora para o commit
                $Timestamp = Get-Date -Format "dd/MM/yyyy HH:mm:ss"

                $CommitMessage = "Auto commit - $Timestamp"

                Write-Host "[2/4] Criando commit..."
                Write-Host "       $CommitMessage"

                git commit -m "$CommitMessage"

                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[AVISO] Nenhum commit criado ou ocorreu um erro." -ForegroundColor Yellow
                    continue
                }

                Write-Host "[3/4] Enviando para GitHub..."

                git push $Remote $Branch

                if ($LASTEXITCODE -eq 0) {
                    Write-Host ""
                    Write-Host "[OK] Alteracoes enviadas para o GitHub!" -ForegroundColor Green
                }
                else {
                    Write-Host ""
                    Write-Host "[ERRO] O git push falhou." -ForegroundColor Red
                    Write-Host "Suas alteracoes continuam salvas localmente."
                }

                Write-Host ""

                $LastCommitTime = Get-Date
            }
        }
    }

    # Pequena pausa para evitar uso desnecessario de CPU
    Start-Sleep -Milliseconds 1000
}
```
