import importlib
import importlib.util
import os
import re
import sys
from typing import Callable

# Skill scopes:
#   "all"          — injected everywhere: intent classifier AND orchestrator (default)
#   "orchestrator" — injected ONLY into the planner/executor, NEVER into the intent classifier
#   "classifier"   — injected ONLY into the intent classifier
SCOPE_ALL = "all"
SCOPE_ORCHESTRATOR = "orchestrator"
SCOPE_CLASSIFIER = "classifier"


def _skill_search_dirs(project_path: str = "") -> list[str]:
    """Return skill directories in priority order."""
    dirs = []
    # 1. Project's own skills dir
    if project_path:
        dirs.append(os.path.join(project_path, "skills"))
    # 2. Package skills dir (when installed via wheel)
    package_dir = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(package_dir, "skills"))
    # 3. Repo root skills dir (when running from source)
    repo_root = os.path.dirname(package_dir)
    dirs.append(os.path.join(repo_root, "skills"))
    # 4. User global skills
    dirs.append(os.path.expanduser("~/.opalacoder/skills"))
    return dirs


def _parse_skill_file(filepath: str) -> dict | None:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    tags_match = re.search(r"^tags:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
    desc_match = re.search(r"^description:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
    scope_match = re.search(r"^scope:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
    reviewer_match = re.search(r"^reviewer:\s*(\S+)", content, re.IGNORECASE | re.MULTILINE)

    # Parse multi-line YAML list under "tools:" until next non-indented key or end
    tools: list[str] = []
    tools_block = re.search(r"^tools:\s*\n((?:[ \t]+-[ \t]+\S+\n?)+)", content, re.IGNORECASE | re.MULTILINE)
    if tools_block:
        for line in tools_block.group(1).splitlines():
            entry = re.sub(r"^[ \t]+-[ \t]+", "", line).strip()
            if entry:
                tools.append(entry)

    tags = [t.strip().lower() for t in tags_match.group(1).split(",") if t.strip()] if tags_match else []
    description = desc_match.group(1).strip() if desc_match else "No description"
    scope = scope_match.group(1).strip().lower() if scope_match else SCOPE_ALL
    reviewer = reviewer_match.group(1).strip() if reviewer_match else None

    clean_content = re.sub(r"^(tags|description|scope|reviewer):\s*.+\n?", "", content, flags=re.IGNORECASE | re.MULTILINE).strip()
    clean_content = re.sub(r"^tools:\s*\n((?:[ \t]+-[ \t]+\S+\n?)+)", "", clean_content, flags=re.IGNORECASE | re.MULTILINE).strip()
    clean_content = re.sub(r"^---\n?", "", clean_content, flags=re.MULTILINE).strip()

    name = os.path.basename(filepath).replace(".md", "")
    return {"name": name, "description": description, "tags": tags, "scope": scope, "tools": tools, "reviewer": reviewer, "content": clean_content}


def _plugin_search_dirs(project_path: str = "") -> list[str]:
    """Return plugin search directories in priority order."""
    dirs = []
    if project_path:
        dirs.append(os.path.join(project_path, "plugins"))
    cwd = os.getcwd()
    if cwd != project_path:
        dirs.append(os.path.join(cwd, ".opalacoder", "plugins"))
    dirs.append(os.path.expanduser("~/.opalacoder/plugins"))
    package_dir = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(package_dir, "plugins"))
    return dirs


def find_plugin_module(module_name: str, project_path: str = "") -> str | None:
    """Return the path to <module_name>.py in plugin search dirs, or None."""
    filename = module_name if module_name.endswith(".py") else f"{module_name}.py"
    for d in _plugin_search_dirs(project_path):
        candidate = os.path.join(d, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def load_skill_tools(project_skills: list[dict], project_path: str = "") -> list[Callable]:
    """Load all tool functions declared in skill frontmatter.

    Each tool entry is "module_name.function_name". The module is located via
    find_plugin_module() and loaded dynamically. Returns a flat list of callables.
    """
    loaded: list[Callable] = []
    seen_modules: dict[str, object] = {}

    for skill in project_skills:
        for tool_ref in skill.get("tools", []):
            parts = tool_ref.rsplit(".", 1)
            if len(parts) != 2:
                continue
            module_name, func_name = parts

            if module_name not in seen_modules:
                mod_path = find_plugin_module(module_name, project_path)
                if mod_path is None:
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(module_name, mod_path)
                    mod = importlib.util.module_from_spec(spec)
                    # Make the module available under its name so relative imports work
                    sys.modules.setdefault(module_name, mod)
                    spec.loader.exec_module(mod)
                    seen_modules[module_name] = mod
                except Exception:
                    continue
            else:
                mod = seen_modules[module_name]

            fn = getattr(mod, func_name, None)
            # Accept both plain callables and FunctionBlock objects (returned by @as_tool)
            if fn is not None and (callable(fn) or hasattr(fn, "run")):
                loaded.append(fn)

    return loaded


def load_skill_reviewers(project_skills: list[dict], project_path: str = "") -> list[Callable]:
    """Load reviewer functions declared in skill frontmatter under `reviewer:`.

    Each reviewer entry is "module_name.function_name". The function must have
    the signature:

        def my_reviewer(project_path: str, task_goal: str,
                        related_files: list[str]) -> dict:
            ...
            return {"done": bool, "summary": str, "corrections": list[str]}

    Returns a flat list of reviewer callables (one per skill that declares one).
    """
    loaded: list[Callable] = []
    seen_modules: dict[str, object] = {}

    for skill in project_skills:
        reviewer_ref = skill.get("reviewer")
        if not reviewer_ref:
            continue
        parts = reviewer_ref.rsplit(".", 1)
        if len(parts) != 2:
            continue
        module_name, func_name = parts

        if module_name not in seen_modules:
            mod_path = find_plugin_module(module_name, project_path)
            if mod_path is None:
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, mod_path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules.setdefault(module_name, mod)
                spec.loader.exec_module(mod)
                seen_modules[module_name] = mod
            except Exception:
                continue
        else:
            mod = seen_modules[module_name]

        fn = getattr(mod, func_name, None)
        if fn is not None and callable(fn):
            loaded.append(fn)

    return loaded


def load_skills(project_path: str = "") -> list[dict]:
    """Load all available skill files from the search dirs."""
    skills = []
    loaded_files: set[str] = set()

    for s_dir in _skill_search_dirs(project_path):
        if not os.path.isdir(s_dir):
            continue
        for filename in sorted(os.listdir(s_dir)):
            if not filename.endswith(".md") or filename in loaded_files:
                continue
            skill = _parse_skill_file(os.path.join(s_dir, filename))
            if skill:
                skills.append(skill)
                loaded_files.add(filename)

    return skills


def load_project_skills(project_path: str, skill_names: list[str]) -> list[dict]:
    """Load only the skills listed in the project's skill_names, always including opalacoder."""
    names = set(skill_names)
    names.add("opalacoder")
    all_skills = load_skills(project_path)
    return [s for s in all_skills if s["name"] in names]


def find_skill_file(skill_name: str, project_path: str = "") -> str | None:
    """Return the path to <skill_name>.md if found in any search dir, else None."""
    filename = skill_name if skill_name.endswith(".md") else f"{skill_name}.md"
    for s_dir in _skill_search_dirs(project_path):
        candidate = os.path.join(s_dir, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


async def select_skills_for_project(model: str, description: str, project_path: str = "") -> list[str]:
    """Use an LLM to pick skills relevant to a new project description. Always includes opalacoder."""
    all_skills = load_skills(project_path)
    catalog = "\n".join(f"- {s['name']}: {s['description']}" for s in all_skills if s['name'] != "opalacoder")
    if not catalog:
        return ["opalacoder"]

    prompt = (
        f"PROJECT DESCRIPTION: {description}\n\n"
        f"AVAILABLE SKILLS:\n{catalog}\n\n"
        "List the skill names (comma-separated) that are relevant to this project. "
        "Reply with skill names only, nothing else."
    )

    from .agents import make_skill_selector
    from agenticblocks.blocks.llm.agent import AgentInput

    selector = make_skill_selector(model)
    try:
        result = await selector.run(AgentInput(prompt=prompt))
        selected = [w.strip().lower() for w in result.response.replace("\n", ",").split(",") if w.strip()]
        valid_names = {s["name"].lower(): s["name"] for s in all_skills}
        chosen = ["opalacoder"] + [valid_names[n] for n in selected if n in valid_names and valid_names[n] != "opalacoder"]
        return chosen if chosen else ["opalacoder"]
    except Exception:
        return ["opalacoder"]


def _filter_by_scope(skills: list, target_scope: str) -> list:
    """Return only skills that are allowed in the given target context."""
    if target_scope == SCOPE_CLASSIFIER:
        # Classifier gets: scope=all and scope=classifier
        return [s for s in skills if s["scope"] in (SCOPE_ALL, SCOPE_CLASSIFIER)]
    elif target_scope == SCOPE_ORCHESTRATOR:
        # Orchestrator gets: scope=all and scope=orchestrator
        return [s for s in skills if s["scope"] in (SCOPE_ALL, SCOPE_ORCHESTRATOR)]
    # Fallback: return all
    return skills


def get_relevant_skills(text: str, scope: str = SCOPE_ALL, project_skills: list[dict] = None) -> str:
    """Keyword-matching skill selector. Uses project_skills if provided."""
    skills = _filter_by_scope(project_skills if project_skills is not None else load_skills(), scope)
    if not skills:
        return ""

    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    injected_contents = []

    for skill in skills:
        for tag in skill["tags"]:
            if (tag in words) or (" " in tag and tag in text_lower):
                injected_contents.append(f"--- REFERENCE MATERIAL: {skill['name']} (Use ONLY if applicable to the task) ---\n{skill['content']}")
                break

    if not injected_contents:
        return ""

    return "\nOPTIONAL BEST PRACTICES / REFERENCE:\n" + "\n\n".join(injected_contents)


async def get_relevant_skills_llm(model: str, request: str, scope: str = SCOPE_ALL, project_skills: list[dict] = None) -> str:
    """LLM-based semantic skill selector. Uses project_skills if provided."""
    skills = _filter_by_scope(project_skills if project_skills is not None else load_skills(), scope)
    if not skills:
        return ""

    skills_catalog = "\n".join([f"- {s['name']}: {s['description']}" for s in skills])
    prompt = f"USER REQUEST: {request}\n\nAVAILABLE SKILLS:\n{skills_catalog}"

    from .agents import make_skill_selector
    from agenticblocks.blocks.llm.agent import AgentInput
    from . import terminal as T

    T.thinking("Selecting skill context (Semantic Router)...")
    selector = make_skill_selector(model)
    try:
        result = await selector.run(AgentInput(prompt=prompt))
        selected_text = result.response.lower()
    except Exception as e:
        T.error(f"Skill router error: {e}")
        return ""

    injected_contents = []
    selected_skill_names = []
    for skill in skills:
        if skill["name"].lower() in selected_text:
            injected_contents.append(f"--- REFERENCE MATERIAL: {skill['name']} (Use ONLY if applicable to the task) ---\n{skill['content']}")
            selected_skill_names.append(skill["name"])

    if not injected_contents:
        return ""

    T.info(f"Active skills: {', '.join(selected_skill_names)}")
    return "\nOPTIONAL BEST PRACTICES / REFERENCE:\n" + "\n\n".join(injected_contents)
