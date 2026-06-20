$ErrorActionPreference = "Stop"

Write-Host "=========================================="
Write-Host "       OmniMe - Build do Executável       "
Write-Host "=========================================="

Write-Host "`n[1/4] Instalando PyInstaller e dependências..."
pip install pyinstaller wheel setuptools

Write-Host "`n[2/4] Construindo o frontend (React/Vite)..."
Push-Location gui_src
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

Write-Host "`n[3/4] Limpando diretórios de build antigos..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

Write-Host "`n[4/4] Empacotando com PyInstaller..."
# A sintaxe de --add-data no Windows usa ponto-e-vírgula (;)
pyinstaller --name "OmniMe" `
            --windowed `
            --icon="icon.png" `
            --add-data="omnime/gui;omnime/gui" `
            --add-data="omnime/assetstore;omnime/assetstore" `
            --add-data="config.yaml;." `
            --add-data="skills;skills" `
            --add-data="version_info.txt;." `
            --collect-all "litellm" `
            --collect-all "chromadb" `
            --collect-all "duckduckgo_search" `
            --collect-all "instructor" `
            --collect-all "agenticblocks" `
            --noconfirm `
            --clean `
            main.py

Write-Host "`n=========================================="
Write-Host "Build concluído com sucesso!"
Write-Host "O executável pode ser encontrado em: .\dist\OmniMe\OmniMe.exe"
Write-Host "=========================================="
