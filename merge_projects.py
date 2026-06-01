import os
import shutil

src_dir = "/home/gilzamir/projetos/opalacoderide"
dst_dir = "/home/gilzamir/projetos/OpalaCoder/gui_src"

# Create destination directory
os.makedirs(dst_dir, exist_ok=True)

# Files and folders to copy
to_copy = ["src", "index.html", "package.json", "package-lock.json"]

for item in to_copy:
    src_path = os.path.join(src_dir, item)
    dst_path = os.path.join(dst_dir, item)
    
    if os.path.exists(dst_path):
        try:
            if os.path.isdir(dst_path):
                shutil.rmtree(dst_path)
            else:
                os.remove(dst_path)
        except Exception as e:
            print(f"Error removing {dst_path}: {e}")
            
    if os.path.exists(src_path):
        try:
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
            print(f"Copied {item} to gui_src.")
        except Exception as e:
            print(f"Error copying {item}: {e}")
            
print("Successfully merged GUI source code to gui_src.")
