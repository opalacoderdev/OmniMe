import os
import sys
import argparse
import shutil

def validate_path(path, project_path):
    project_path = os.path.abspath(project_path)
    abs_path = os.path.abspath(os.path.join(project_path, path))
    if not abs_path.startswith(project_path):
        print(f"Error: Path '{path}' is outside project directory '{project_path}'", file=sys.stderr)
        sys.exit(1)
    return abs_path

def main():
    parser = argparse.ArgumentParser(description="Command-line executor for files and directories")
    parser.add_argument("--project-path", default=os.getcwd(), help="Path to the project workspace")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # create-file
    p_create_file = subparsers.add_parser("create-file")
    p_create_file.add_argument("path", help="Relative file path")
    p_create_file.add_argument("--content", default="", help="Initial content")
    
    # insert-text
    p_insert_text = subparsers.add_parser("insert-text")
    p_insert_text.add_argument("path", help="Relative file path")
    p_insert_text.add_argument("--content", required=True, help="Content to insert")
    p_insert_text.add_argument("--line", type=int, help="Line number (1-indexed) to insert before. If omitted, appends to the file.")
    
    # remove-file
    p_remove_file = subparsers.add_parser("remove-file")
    p_remove_file.add_argument("path", help="Relative file path")
    
    # create-dir
    p_create_dir = subparsers.add_parser("create-dir")
    p_create_dir.add_argument("path", help="Relative directory path")
    
    # remove-dir
    p_remove_dir = subparsers.add_parser("remove-dir")
    p_remove_dir.add_argument("path", help="Relative directory path")
    
    args = parser.parse_args()
    
    if args.command == "create-file":
        target = validate_path(args.path, args.project_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(args.content)
        print(f"File created successfully: {args.path}")
        
    elif args.command == "insert-text":
        target = validate_path(args.path, args.project_path)
        if not os.path.exists(target):
            print(f"Error: File '{args.path}' does not exist.", file=sys.stderr)
            sys.exit(1)
            
        with open(target, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        content = args.content
        if not content.endswith('\n'):
            content += '\n'
            
        if args.line is not None:
            idx = max(0, min(args.line - 1, len(lines)))
            lines.insert(idx, content)
        else:
            lines.append(content)
            
        with open(target, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Text inserted successfully into {args.path}")
        
    elif args.command == "remove-file":
        target = validate_path(args.path, args.project_path)
        if os.path.isdir(target):
            print(f"Error: Path '{args.path}' is a directory, use remove-dir instead.", file=sys.stderr)
            sys.exit(1)
        if os.path.exists(target):
            os.remove(target)
            print(f"File removed successfully: {args.path}")
        else:
            print(f"Error: File '{args.path}' does not exist.", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "create-dir":
        target = validate_path(args.path, args.project_path)
        os.makedirs(target, exist_ok=True)
        print(f"Directory created successfully: {args.path}")
        
    elif args.command == "remove-dir":
        target = validate_path(args.path, args.project_path)
        if not os.path.isdir(target):
            print(f"Error: Path '{args.path}' is not a directory.", file=sys.stderr)
            sys.exit(1)
        if os.path.exists(target):
            shutil.rmtree(target)
            print(f"Directory removed successfully: {args.path}")
        else:
            print(f"Error: Directory '{args.path}' does not exist.", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
