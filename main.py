"""OmniMe entry point — run with: python main.py [--mode auto|plan|edit] [--model ...]"""
import sys

# Force UTF-8 on Windows to prevent 'charmap' codec crashes when printing emojis or unicode
if sys.stdout and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
if sys.stderr and getattr(sys.stderr, "encoding", "").lower() != "utf-8":
    try: sys.stderr.reconfigure(encoding="utf-8")
    except Exception: pass

import os
# PyInstaller + PythonNet workaround: explicitly set the python DLL path 
# so pythonnet can initialize correctly on other machines
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(sys._MEIPASS)
    
    import glob
    import ctypes
    python_dlls = glob.glob(os.path.join(sys._MEIPASS, 'python3*.dll'))
    if python_dlls:
        os.environ["PYTHONNET_PYDLL"] = python_dlls[0]
        try:
            ctypes.CDLL(python_dlls[0])
        except Exception:
            pass



from omnime.cli import main

if __name__ == "__main__":
    main()
