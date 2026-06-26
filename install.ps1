# =========================================================
# Script de Instalação do OmniMe para Windows (via PowerShell)
# =========================================================
#
# Atalhos criados:
#   - Desktop do usuário              (~\Desktop\OmniMe.lnk)
#   - Menu Iniciar do usuário         (~\AppData\...\Programs\OmniMe.lnk)

$ErrorActionPreference = "Stop"

# 1. Configurações Iniciais
$installDir = "$env:LOCALAPPDATA\OmniMe"
$tempZip = "$env:TEMP\omnime_release.zip"

# Link para baixar a release mais recente do repositório oficial
$downloadUrl = "https://github.com/opalacoderdev/OmniMe/releases/latest/download/OmniMe-windows-x64.zip"

Write-Host "Iniciando a instalacao do OmniMe..." -ForegroundColor Cyan

# 2. Criar diretório de instalação
if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
}

# 3. Baixar o arquivo
Write-Host "Baixando a ultima versao do OmniMe (isso pode levar alguns minutos)..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $downloadUrl -OutFile $tempZip -UseBasicParsing

# 4. Extrair os arquivos
Write-Host "Extraindo arquivos para $installDir..." -ForegroundColor Yellow
# O parâmetro -Force sobrescreve versões antigas se o usuário estiver atualizando
Expand-Archive -Path $tempZip -DestinationPath $installDir -Force

# Como o zip gerado na Action foi feito a partir de "dist\OmniMe",
# o Expand-Archive criará a pasta "$installDir\OmniMe". Vamos renomear ou ajustar o PATH.
# Se existir $installDir\OmniMe, o exe estará em $installDir\OmniMe\OmniMe.exe
$exeDir = "$installDir\OmniMe"
if (-not (Test-Path "$exeDir\OmniMe.exe")) {
    $exeDir = $installDir
}

# 5. Adicionar a pasta do OmniMe na variável PATH do Windows (se já não estiver)
$userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
if ($userPath -notlike "*$exeDir*") {
    Write-Host "Adicionando OmniMe ao seu PATH..." -ForegroundColor Yellow
    $newPath = "$userPath;$exeDir"
    [Environment]::SetEnvironmentVariable("Path", $newPath, [EnvironmentVariableTarget]::User)
    $env:Path = "$env:Path;$exeDir"
}

# 6. Criar atalhos (Desktop e Menu Iniciar)
Write-Host "Criando atalhos..." -ForegroundColor Yellow

$exePath  = "$exeDir\OmniMe.exe"
$wshShell = New-Object -ComObject WScript.Shell

# Atalho no Desktop
$desktopShortcut      = $wshShell.CreateShortcut("$env:USERPROFILE\Desktop\OmniMe.lnk")
$desktopShortcut.TargetPath       = $exePath
$desktopShortcut.WorkingDirectory = $exeDir
$desktopShortcut.Description      = "OmniMe AI Assistant"
$desktopShortcut.IconLocation     = "$exePath,0"
$desktopShortcut.Save()

# Atalho no Menu Iniciar
$startMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
if (-not (Test-Path $startMenuDir)) {
    New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
}
$startMenuShortcut      = $wshShell.CreateShortcut("$startMenuDir\OmniMe.lnk")
$startMenuShortcut.TargetPath       = $exePath
$startMenuShortcut.WorkingDirectory = $exeDir
$startMenuShortcut.Description      = "OmniMe AI Assistant"
$startMenuShortcut.IconLocation     = "$exePath,0"
$startMenuShortcut.Save()

Write-Host "  -> Desktop: $env:USERPROFILE\Desktop\OmniMe.lnk" -ForegroundColor DarkGray
Write-Host "  -> Menu Iniciar: $startMenuDir\OmniMe.lnk" -ForegroundColor DarkGray

# 7. Limpeza
Write-Host "Limpando arquivos temporarios..." -ForegroundColor DarkGray
Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue

# 8. Finalização
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  OmniMe instalado/atualizado com sucesso!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Atalhos criados:"
Write-Host "  - Desktop" -ForegroundColor Cyan
Write-Host "  - Menu Iniciar" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para abrir o OmniMe pelo terminal:"
Write-Host "  omnime" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nota: Se o comando nao for reconhecido, feche este terminal e abra um novo."
