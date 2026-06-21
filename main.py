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
import subprocess

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

    # Add the specific pywinpty bin directory to PATH so winpty-agent.exe can be found
    meipass = sys._MEIPASS
    winpty_dir = None
    for root, dirs, files in os.walk(meipass):
        if 'winpty-agent.exe' in files:
            winpty_dir = root
            break
            
    if winpty_dir:
        try:
            os.environ["PATH"] = winpty_dir + os.pathsep + os.environ.get("PATH", "")
        except ValueError:
            # Fallback if PATH exceeds Windows 32K limit
            pass



# Prevent command prompt windows from flashing when using subprocess in --windowed mode on Windows
if sys.platform == "win32":
    _orig_popen_init = subprocess.Popen.__init__
    def _patched_popen_init(self, *args, **kwargs):
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _patched_popen_init




from omnime.cli import main

if __name__ == "__main__":
    main()
