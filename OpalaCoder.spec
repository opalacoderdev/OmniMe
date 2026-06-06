# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys
import os

binaries = []
hiddenimports = ["chromadb", "tiktoken_ext.openai_public", "tiktoken_ext.anthropic"] + collect_submodules('webview')

if sys.platform == 'win32':
    # Add windows specific binaries
    try:
        import winpty
        winpty_dir = os.path.dirname(winpty.__file__)
        for filename in os.listdir(winpty_dir):
            if filename.endswith(".dll") or filename.endswith(".exe"):
                binaries.append((os.path.join(winpty_dir, filename), "winpty"))
    except ImportError:
        pass
        
    try:
        import webview
        webview_dir = os.path.dirname(webview.__file__)
        webview2_loader = os.path.join(webview_dir, "lib", "runtimes", "win-x64", "native", "WebView2Loader.dll")
        if os.path.exists(webview2_loader):
            binaries.append((webview2_loader, "."))
    except ImportError:
        pass

    hiddenimports.extend(["clr", "clr_loader"])

a = Analysis(
    ['main.py'],
    datas=[
        ("config.yaml",       "."),
        ("skills/*",          "skills"),
        ("opalacoder/gui/",   "opalacoder/gui"),
    ] + collect_data_files('litellm') + collect_data_files('tiktoken'),
    binaries=binaries,
    hiddenimports=hiddenimports,
    pathex=[],
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
    name='OpalaCoder',
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
    icon=['icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpalaCoder',
)
