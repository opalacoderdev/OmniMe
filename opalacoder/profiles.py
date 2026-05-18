import os
import yaml
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from agenticblocks.core.agent import AgentBlock
from agenticblocks.blocks.llm.agent import LLMAgentBlock

def load_profiles(profiles_dir: str = "profiles") -> Dict[str, Any]:
    """
    Scans the profiles directory and parses valid YAML profiles.
    Returns a dict mapping filename to the parsed profile config.
    """
    profiles = {}
    if not os.path.isdir(profiles_dir):
        return profiles
        
    for filename in os.listdir(profiles_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(profiles_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "match_description" in data and "tasks" in data:
                        profiles[filename] = data
            except Exception as e:
                import rich.console
                rich.console.Console().print(f"[red]Failed to load profile {filename}: {e}[/red]")
    return profiles


from .structured import StructuredLLMAgentBlock

class ProfileSelection(BaseModel):
    profile_filename: Optional[str] = Field(
        default=None,
        description="The filename of the chosen profile (e.g. 'frontend_react_vite.yaml'), or None/null if no profile matches perfectly."
    )
    reasoning: str = Field(description="Explanation of why this profile was chosen or rejected.")

async def resolve_profile(user_request: str, profiles: Dict[str, Any], model: str) -> Optional[str]:
    """
    Uses a StructuredLLMAgentBlock to select the most appropriate profile for the user_request.
    """
    if not profiles:
        return None

    options_text = "Available Profiles:\n\n"
    for filename, data in profiles.items():
        options_text += f"- Filename: {filename}\n  Description: {data.get('match_description', '')}\n\n"

    prompt = (
        f"You are an orchestrator routing system.\n"
        f"The user wants to do the following task:\n<USER_TASK>\n{user_request}\n</USER_TASK>\n\n"
        f"Please review the available profiles and their descriptions to determine if one is a PERFECT match.\n"
        f"{options_text}\n"
        f"Select the best fitting profile, or set it to null/None if no profile is a robust match."
    )

    agent = StructuredLLMAgentBlock(
        name="ProfileResolver",
        model=model,
        system_prompt="You are an expert routing AI that matches user intents to predefined execution profiles.",
        response_schema=ProfileSelection
    )

    try:
        from agenticblocks.blocks.llm.agent import AgentInput
        res = await agent.run(AgentInput(prompt=prompt))
        if res.structured_output and res.structured_output.profile_filename:
            filename = res.structured_output.profile_filename.strip()
            import rich.console
            rich.console.Console().print(f"[blue]Profile Resolver Reasoning: {res.structured_output.reasoning}[/blue]")
            if filename in profiles:
                rich.console.Console().print(f"[blue]Profile Resolver Selected: {filename}[/blue]")
                return filename
    except Exception as e:
        import rich.console
        rich.console.Console().print(f"[red]Error resolving profile: {e}[/red]")
    
    return None

async def infer_system_prompt(task_label: str, task_desc: str, model: str) -> str:
    """
    Infers a system prompt for an agent given its task description.
    """
    prompt = (
        f"You need to write a system prompt for an autonomous coding agent.\n"
        f"The agent's specific task is: '{task_label}' - {task_desc}\n\n"
        f"Write a concise but robust system prompt telling the agent what its role is, "
        f"and emphasizing that it must use its available tools to accomplish the task."
    )
    
    agent = LLMAgentBlock(
        name="PromptInferer",
        model=model,
        system_prompt="You are a system prompt engineer. Provide ONLY the raw text of the prompt."
    )
    
    try:
        from agenticblocks.blocks.llm.agent import AgentInput
        res = await agent.run(AgentInput(prompt=prompt))
        return res.response.strip()
    except Exception:
        return "You are an autonomous AI coding agent. Complete your assigned task using tools."
