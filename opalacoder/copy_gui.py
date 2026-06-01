import os
import shutil

src = "/home/gilzamir/projetos/opalacoderide/dist"
dst = "/home/gilzamir/projetos/OpalaCoder/opalacoder/gui"

if os.path.exists(dst):
    try:
        shutil.rmtree(dst)
    except Exception as e:
        print(f"Error removing existing destination: {e}")
    
if os.path.exists(src):
    try:
        shutil.copytree(src, dst)
        print("GUI assets copied successfully to:", dst)
    except Exception as e:
        print(f"Error copying directory tree: {e}")
else:
    print(f"Source directory '{src}' does not exist. Please run 'npm run build' first.")
