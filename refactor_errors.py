import re
import sys

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace `return "Error...` and `return f"Error...` with `raise ValueError("Error...` and `raise ValueError(f"Error...`
    # Match: return followed by spaces, then optional 'f', then "Error or 'Error (case insensitive)
    # Then capture until the end of the string literal
    
    def replacer(match):
        indent = match.group(1)
        # We need to capture the whole return expression and wrap it in raise ValueError( ... )
        return indent + "raise ValueError(" + match.group(2) + ")"

    # Regex to find `return <string starting with Error>`
    # It might be safer to match `return f"Error` and the rest of the line.
    # Note that some returns might span multiple lines if they are parenthesized or have implicit concatenation.
    # Fortunately, the ones I've seen are on a single line.
    
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if re.search(r'^\s*return\s+f?["\'](?i:error)', line):
            # Replace return with raise ValueError(
            line = re.sub(r'^(\s*)return\s+(f?["\'].*?["\'](?:\.format\(.*?\))?)$', r'\1raise ValueError(\2)', line)
        new_lines.append(line)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')

process_file('opalacoder/tools.py')
process_file('opalacoder/workflow_tools.py')
