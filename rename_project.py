import os
import shutil

# Extensions to modify
EXTENSIONS = {".py", ".yaml", ".md", ".json", ".toml", ".txt"}

# Ignored directories
IGNORE_DIRS = {".git", ".env", ".venv", "node_modules", "__pycache__", ".pytest_cache"}

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        new_content = content.replace('OpalaCoder', 'OpalaCoder')
        new_content = new_content.replace('opalacoder', 'opalacoder')
        new_content = new_content.replace('OPALA_', 'OPALA_')
        new_content = new_content.replace('.opalacoder', '.opalacoder')
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {filepath}")
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

def main():
    root_dir = os.path.abspath(os.path.dirname(__file__))
    
    # 1. Replace text in files
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        
        for filename in filenames:
            ext = os.path.splitext(filename)[1]
            if ext in EXTENSIONS or filename == 'main.py' or filename == '.gitignore':
                filepath = os.path.join(dirpath, filename)
                replace_in_file(filepath)
                
    # 2. Rename directories and specific files
    opalacoder_dir = os.path.join(root_dir, 'opalacoder')
    opalacoder_dir = os.path.join(root_dir, 'opalacoder')
    
    if os.path.exists(opalacoder_dir) and os.path.isdir(opalacoder_dir):
        shutil.move(opalacoder_dir, opalacoder_dir)
        print(f"Renamed directory: {opalacoder_dir} -> {opalacoder_dir}")
        
    opalacoder_skill = os.path.join(root_dir, 'skills', 'opalacoder.md')
    opalacoder_skill = os.path.join(root_dir, 'skills', 'opalacoder.md')
    
    if os.path.exists(opalacoder_skill):
        shutil.move(opalacoder_skill, opalacoder_skill)
        print(f"Renamed file: {opalacoder_skill} -> {opalacoder_skill}")

if __name__ == '__main__':
    main()
