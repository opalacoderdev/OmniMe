#!/bin/bash
set -e

echo "=========================================="
echo "       OmniMe - Build do Executável (Linux) "
echo "=========================================="

echo -e "\n[1/4] Instalando PyInstaller e dependências..."
pip install pyinstaller wheel setuptools

echo -e "\n[2/4] Construindo o frontend (React/Vite)..."
cd gui_src
npm install
npm run build
cd ..

echo -e "\n[3/4] Limpando diretórios de build antigos..."
rm -rf build dist

echo -e "\n[4/4] Empacotando com PyInstaller..."
# A sintaxe de --add-data no Linux usa dois pontos (:)
pyinstaller --name "OmniMe" \
            --windowed \
            --icon="icon.png" \
            --add-data="omnime/gui:omnime/gui" \
            --add-data="omnime/assetstore:omnime/assetstore" \
            --add-data="config.yaml:." \
            --add-data="skills:skills" \
            --add-data="version_info.txt:." \
            --collect-all "litellm" \
            --collect-all "tiktoken" \
            --collect-all "tiktoken_ext" \
            --copy-metadata "tiktoken" \
            --collect-all "certifi" \
            --collect-all "httpx" \
            --collect-all "aiohttp" \
            --collect-all "requests" \
            --collect-all "chromadb" \
            --collect-all "duckduckgo_search" \
            --collect-all "instructor" \
            --collect-all "agenticblocks" \
            --collect-all "webview" \
            --collect-all "pythonnet" \
            --collect-all "clr_loader" \
            --collect-all "PyQt6" \
            --collect-all "PyQt6-WebEngine" \
            --noconfirm \
            --clean \
            main.py

echo -e "\n=========================================="
echo "Build concluído com sucesso!"
echo "O executável pode ser encontrado em: ./dist/OmniMe/OmniMe"
echo "=========================================="
