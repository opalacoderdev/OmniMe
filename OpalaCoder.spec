# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['main.py'],
    datas=[
        ("agents.yaml",       "."),
        ("config.yaml",       "."),
        ("skills/",           "skills"),
        ("opalacoder/gui/",   "opalacoder/gui"),
        # recursos do Chromium:
        ("C:/Users/gilza/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/LocalCache/local-packages/Python312/site-packages/PyQt6/Qt6/resources/","PyQt6/Qt6/resources"),
        ("C:/Users/gilza/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/LocalCache/local-packages/Python312/site-packages/PyQt6/Qt6/translations/qtwebengine_locales/",
         "PyQt6/Qt6/translations/qtwebengine_locales"),
    ] + collect_data_files('litellm') + collect_data_files('tiktoken'),
    binaries=[
        ("C:/Users/gilza/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/LocalCache/local-packages/Python312/site-packages/PyQt6/Qt6/bin/QtWebEngineProcess.exe", "PyQt6/Qt6/bin"),
    ],
    hiddenimports=["PyQt6.QtWebEngineWidgets", "chromadb", "tiktoken_ext.openai_public", "tiktoken_ext.anthropic", "clr", "clr_loader"] + collect_submodules('webview'),
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
# OpalaCoder.spec

