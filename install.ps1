# =========================================================
# Script de Instalação do OmniMe para Windows (via PowerShell)
# =========================================================

$ErrorActionPreference = "Stop"

# 1. Configurações Iniciais
$installDir = "$env:LOCALAPPDATA\OmniMe"
$tempZip = "$env:TEMP\omnime_release.zip"

# Link para baixar a release mais recente do repositório oficial
$downloadUrl = "https://github.com/omnimedev/OmniMe/releases/latest/download/OmniMe-windows-x64.zip"

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

# 6. Limpeza
Write-Host "Limpando arquivos temporarios..." -ForegroundColor DarkGray
Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue

# 7. Finalização
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  OmniMe instalado/atualizado com sucesso!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para abrir o OmniMe agora, basta digitar em um terminal:"
Write-Host "  omnime" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nota: Se o comando não for reconhecido, feche este terminal e abra um novo."
