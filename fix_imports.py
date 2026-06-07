import os

def fix_imports(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Simple replacement: `from .` -> `from opalacoder.`
    # EXCEPT for workflow_tools and workflow_orchestrator
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith("from ."):
            if "workflow_tools" in line:
                lines[i] = line.replace("from .workflow_tools", "from workflow_tools")
            elif "workflow_orchestrator" in line:
                lines[i] = line.replace("from .workflow_orchestrator", "from workflow_orchestrator")
            elif "import terminal as T" in line:
                lines[i] = line.replace("from . import terminal as T", "from opalacoder import terminal as T")
            else:
                lines[i] = line.replace("from .", "from opalacoder.")
        elif line.strip().startswith("from ."):
            # Indented imports
            if "workflow_tools" in line:
                lines[i] = line.replace("from .workflow_tools", "from workflow_tools")
            elif "workflow_orchestrator" in line:
                lines[i] = line.replace("from .workflow_orchestrator", "from workflow_orchestrator")
            elif "import terminal as T" in line:
                lines[i] = line.replace("from . import terminal as T", "from opalacoder import terminal as T")
            else:
                lines[i] = line.replace("from .", "from opalacoder.")

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

base = "skills/skills_store/implement-feature/scripts"
fix_imports(f"{base}/workflow_orchestrator.py")
fix_imports(f"{base}/workflow_tools.py")
fix_imports(f"{base}/run_workflow.py")
