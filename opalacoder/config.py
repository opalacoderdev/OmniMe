"""Global configuration defaults for OpalaCoder."""

import os
import yaml
import pathlib
from dotenv import load_dotenv

# Load local .env
load_dotenv()

# Suppress the non-fatal LiteLLM logging worker warning (coroutine never awaited)
# which frequently occurs in asynchronous contexts on newer Python versions.
import warnings
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message=".*coroutine 'Logging.async_success_handler' was never awaited.*"
)

# Load global .env
global_env = pathlib.Path.home() / ".opalacoder" / ".env"
if global_env.exists():
    load_dotenv(dotenv_path=global_env)

def _load_agents_config() -> dict:
    # Search for agents.yaml next to this file (project root), then fall back to cwd.
    candidates = [
        pathlib.Path(__file__).parent / "agents.yaml",
        pathlib.Path(__file__).parent.parent / "agents.yaml",
        pathlib.Path(os.getcwd()) / "agents.yaml",
    ]
    for config_path in candidates:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Warning: Failed to parse {config_path}: {e}")
    return {}

_AGENTS_CONFIG = _load_agents_config()

# Model used for all agents (can be overridden via CLI --model)
DEFAULT_MODEL = _AGENTS_CONFIG.get("default", os.getenv("OPALA_MODEL", "ollama/mistral-nemo"))
ALTERNATIVE_MODEL = _AGENTS_CONFIG.get("alternative", "gemini/gemini-3.1-flash-lite")

# Global LLM defaults (temperature, max_tokens, num_ctx) — can be set in agents.yaml
_LLM_DEFAULTS: dict = {
    "temperature": 0.7,
    "max_tokens": 4096,
    "num_ctx": 8192,
    **_AGENTS_CONFIG.get("llm_defaults", {}),
}

# Per-agent overrides loaded from agents.yaml
_AGENT_OVERRIDES: dict[str, dict] = _AGENTS_CONFIG.get("agents", {})


# Fields that are consumed outside of litellm kwargs and must not be forwarded.
_NON_LITELLM_FIELDS = {"model", "max_heartbeats", "debug", "strategy"}


from typing import Union

def get_git_strategy() -> str:
    """Return the git strategy configured in agents.yaml ('hybrid', 'agent_driven', 'auto', 'none')."""
    return _AGENTS_CONFIG.get("git_strategy", "hybrid")

def get_complexity_inference_mode() -> str:
    """Return the complexity inference mode (simple or double)."""
    return _AGENTS_CONFIG.get("complexity_inference_mode", "simple")

def get_agent_max_heartbeats(agent_name: str, default: int) -> Union[int, str]:
    """Return max_heartbeats configured for *agent_name* in agents.yaml (can be 'auto'), or *default*."""
    val = _AGENT_OVERRIDES.get(agent_name, {}).get("max_heartbeats", default)
    if val == "auto":
        return "auto"
    return int(val)


def get_agent_debug(agent_name: str, default: bool = False) -> bool:
    """Return debug flag configured for *agent_name* in agents.yaml, or *default*."""
    return bool(_AGENT_OVERRIDES.get(agent_name, {}).get("debug", default))


def get_agent_model(agent_name: str, default: str | None = None) -> str:
    """Return the model configured for *agent_name* in agents.yaml, or *default*."""
    override = _AGENT_OVERRIDES.get(agent_name, {}).get("model")
    if override:
        return override
    return default if default is not None else DEFAULT_MODEL


def get_agent_llm_kwargs(agent_name: str) -> dict:
    """Return merged litellm kwargs for *agent_name*.

    Priority (highest first):
      1. Per-agent override in agents.yaml ``agents.<name>``
      2. Global ``llm_defaults`` in agents.yaml
      3. Hard-coded defaults above

    Non-litellm fields (model, max_heartbeats) are excluded.
    """
    merged = dict(_LLM_DEFAULTS)
    merged.update(_AGENT_OVERRIDES.get(agent_name, {}))
    for field in _NON_LITELLM_FIELDS:
        merged.pop(field, None)
    return merged

# Maximum retry attempts for a failing subplan step
DEFAULT_MAX_RETRIES = 3

# MemGPT heartbeat budget per planning turn
DEFAULT_MAX_HEARTBEATS = 15

# SQLite database file for session persistence
DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".opalacoder", "sessions.db"
)

# Execution mode: "auto" | "plan" | "edit"
DEFAULT_MODE = "plan"

def _get_system_lang() -> str:
    env_lang = os.getenv("OPALA_LANG")
    if env_lang in ("en", "pt"):
        return env_lang
        
    try:
        for var in ("LC_ALL", "LC_CTYPE", "LANG"):
            val = os.getenv(var)
            if val and len(val) >= 2:
                lang_code = val[:2].lower()
                if lang_code in ("en", "pt"):
                    return lang_code
                    
        import locale
        loc, _ = locale.getdefaultlocale()
        if loc and len(loc) >= 2:
            lang_code = loc[:2].lower()
            if lang_code in ("en", "pt"):
                return lang_code
    except Exception:
        pass
        
    return "en"

# Default Language
DEFAULT_LANG = _get_system_lang()

# Default litellm kwargs applied to all local model calls (kept for back-compat)
LITELLM_DEFAULTS: dict = {"num_ctx": _LLM_DEFAULTS["num_ctx"]}

# Sensitive operations that require user approval in "edit" mode
SENSITIVE_OPS = {
    "write_file", "delete_file", "run_shell",
    "send_network_request", "create_user", "delete_user",
}

# ─── Debug Logging ────────────────────────────────────────────────────────────

def setup_litellm_debug():
    import litellm
    import logging
    from datetime import datetime
    
    log_dir = os.path.join(os.path.expanduser("~"), ".opalacoder", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "llm_debug.log")
    
    # Configure litellm to use our logger
    litellm.set_verbose = True
    
    logger = logging.getLogger("LiteLLM")
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter('\n' + '='*80 + '\n[%(asctime)s] %(message)s\n' + '='*80)
    fh.setFormatter(formatter)
    
    # Remove existing handlers to avoid duplicates if called multiple times
    if logger.handlers:
        logger.handlers.clear()
        
    logger.addHandler(fh)
    
    # Custom callback to capture inputs and outputs cleanly
    def custom_callback(
        kwargs, completion_response, start_time, end_time
    ):
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        
        log_text = f"MODEL: {model}\n\n=== PROMPT ===\n"
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            log_text += f"[{role}]:\n{content}\n\n"
            
        if completion_response:
            try:
                response_text = completion_response.choices[0].message.content
                log_text += f"=== RESPONSE ===\n{response_text}"
            except Exception:
                log_text += f"=== RAW RESPONSE ===\n{completion_response}"
                
        logger.debug(log_text)

    litellm.success_callback = [custom_callback]
    litellm.failure_callback = [custom_callback]

