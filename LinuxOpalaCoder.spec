# -*- mode: python ; coding: utf-8 -*-
# LinuxOpalaCoder.spec — build for Linux x86_64
#
# Usage:
#   source .env/bin/activate
#   pip install pyinstaller
#   pyinstaller LinuxOpalaCoder.spec
#
# Output: dist/OpalaCoder/  (self-contained, zip to distribute)

import os, sys
from PyInstaller.utils.hooks import collect_data_files

PYQT6 = os.path.join(
    os.path.dirname(sys.executable),   # .env/bin  →  strip to site-packages
    "..", "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages", "PyQt6",
)
PYQT6 = os.path.normpath(PYQT6)

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[
        ("agents.yaml",       "."),
        ("config.yaml",       "."),
        ("skills/",           "skills"),
        ("opalacoder/gui/",   "opalacoder/gui"),
        # QtWebEngine Chromium resources
        (os.path.join(PYQT6, "Qt6", "resources"),
         "PyQt6/Qt6/resources"),
        (os.path.join(PYQT6, "Qt6", "translations", "qtwebengine_locales"),
         "PyQt6/Qt6/translations/qtwebengine_locales"),
    ] + collect_data_files("litellm") + collect_data_files("tiktoken"),
    binaries=[
        # QtWebEngineProcess is a separate Chromium subprocess — not auto-detected
        (os.path.join(PYQT6, "Qt6", "libexec", "QtWebEngineProcess"),
         "PyQt6/Qt6/libexec"),
    ],
    hiddenimports=[
        "PyQt6.QtWebEngineWidgets",
        "chromadb",
        "tiktoken_ext.openai_public",
        "tiktoken_ext.anthropic",
        "webview",
        "webview.platforms.qt",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpalaCoder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["icon.png"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OpalaCoder",
)
