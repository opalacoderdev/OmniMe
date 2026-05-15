import os
import re

def load_skills():
    """Lê arquivos markdown dos diretórios de skills e retorna uma lista de dicionários com tags, descrição e conteúdo."""
    skills = []
    
    # Busca na raiz do projeto e na pasta global ~/.abcode/skills
    skills_dirs = [
        os.path.join(os.getcwd(), "skills"),
        os.path.expanduser("~/.abcode/skills")
    ]
    
    loaded_files = set()
    
    for s_dir in skills_dirs:
        if not os.path.isdir(s_dir):
            continue
            
        for filename in os.listdir(s_dir):
            if not filename.endswith(".md"):
                continue
            
            # Evita carregar skills com o mesmo nome duas vezes (prioriza a local do projeto)
            if filename in loaded_files:
                continue
                
            filepath = os.path.join(s_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
                
            # Extrai tags e description do cabeçalho
            tags_match = re.search(r"^tags:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
            desc_match = re.search(r"^description:\s*(.+)$", content, re.IGNORECASE | re.MULTILINE)
            
            tags = []
            if tags_match:
                tags = [t.strip().lower() for t in tags_match.group(1).split(",") if t.strip()]
                
            description = desc_match.group(1).strip() if desc_match else "Sem descrição"
                
            # Remove o frontmatter do conteúdo injetado
            clean_content = re.sub(r"^(tags|description):\s*.+\n?", "", content, flags=re.IGNORECASE | re.MULTILINE).strip()
            clean_content = re.sub(r"^---\n?", "", clean_content, flags=re.MULTILINE).strip()
            
            skills.append({
                "name": filename.replace(".md", ""),
                "description": description,
                "tags": tags,
                "content": clean_content
            })
            loaded_files.add(filename)
            
    return skills

def get_relevant_skills(text: str) -> str:
    """Busca skills cujas tags estão presentes no texto (Keyword Matching)."""
    skills = load_skills()
    if not skills:
        return ""
        
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    injected_contents = []
    
    for skill in skills:
        for tag in skill["tags"]:
            if (tag in words) or (" " in tag and tag in text_lower):
                injected_contents.append(f"--- SKILL APLICÁVEL: {skill['name']} ---\n{skill['content']}")
                break
                
    if not injected_contents:
        return ""
        
    return "\nINSTRUÇÕES DE SKILLS ESPECÍFICAS:\n" + "\n\n".join(injected_contents)

async def get_relevant_skills_llm(model: str, request: str) -> str:
    """Usa o Skill Selector LLM para escolher skills baseadas na demanda e retorna o conteúdo delas."""
    skills = load_skills()
    if not skills:
        return ""
        
    skills_catalog = "\n".join([f"- {s['name']}: {s['description']}" for s in skills])
    prompt = f"DEMANDA DO USUÁRIO: {request}\n\nSKILLS DISPONÍVEIS:\n{skills_catalog}"
    
    from .agents import make_skill_selector
    from agenticblocks.blocks.llm.agent import AgentInput
    from . import terminal as T
    
    T.thinking("Selecionando contexto de skills (Roteador Semântico)...")
    selector = make_skill_selector(model)
    try:
        result = await selector.run(AgentInput(prompt=prompt))
        selected_text = result.response.lower()
    except Exception as e:
        T.error(f"Erro no roteador de skills: {e}")
        return ""
        
    injected_contents = []
    for skill in skills:
        if skill['name'].lower() in selected_text:
            injected_contents.append(f"--- SKILL APLICÁVEL: {skill['name']} ---\n{skill['content']}")
            
    if not injected_contents:
        return ""
        
    return "\nINSTRUÇÕES DE SKILLS ESPECÍFICAS:\n" + "\n\n".join(injected_contents)
