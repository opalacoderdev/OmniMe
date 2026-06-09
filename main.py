"""OpalaCoder entry point — run with: python main.py [--mode auto|plan|edit] [--model ...]"""
import sys

# Force UTF-8 on Windows to prevent 'charmap' codec crashes when printing emojis or unicode
if sys.stdout and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
if sys.stderr and getattr(sys.stderr, "encoding", "").lower() != "utf-8":
    try: sys.stderr.reconfigure(encoding="utf-8")
    except Exception: pass

from opalacoder.cli import main

if __name__ == "__main__":
    main()
