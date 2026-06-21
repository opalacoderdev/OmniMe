#!/usr/bin/env bash
set -e

echo "=========================================="
echo "       OmniMe - Build do Executável       "
echo "=========================================="

echo -e "\n[1/4] Instalando dependências e PyInstaller..."
pip install pyinstaller wheel setuptools

echo -e "\n[2/4] Construindo o frontend (React/Vite)..."
pushd gui_src > /dev/null
npm install
npm run build
popd > /dev/null

echo -e "\n[3/4] Limpando diretórios de build antigos..."
rm -rf build

echo -e "\n[4/4] Empacotando com PyInstaller..."
# A sintaxe de --add-data no Linux/macOS usa dois pontos (:)
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
            --collect-all "pymupdf" \
            --collect-all "pymupdf4llm" \
            --collect-all "tree_sitter" \
            --collect-all "tree_sitter_language_pack" \
            --noconfirm \
            --clean \
            main.py

echo -e "\n=========================================="
echo "Build concluído com sucesso!"
echo "O executável pode ser encontrado em: ./dist/OmniMe/OmniMe"
echo "=========================================="
