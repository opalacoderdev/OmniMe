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

def _load_yaml(filename: str) -> dict:
    candidates = [
        pathlib.Path(__file__).parent / filename,
        pathlib.Path(__file__).parent.parent / filename,
        pathlib.Path(os.getcwd()) / filename,
    ]
    for config_path in candidates:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Warning: Failed to parse {config_path}: {e}")
    return {}

_AGENTS_CONFIG = _load_yaml("agents.yaml")
_APP_CONFIG = _load_yaml("config.yaml")

# Model used for all agents (can be overridden via CLI --model)
DEFAULT_MODEL = _AGENTS_CONFIG.get("default", os.getenv("OPALA_MODEL", "ollama/ministral-3:14b"))
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
_NON_LITELLM_FIELDS = {"model", "max_heartbeats", "debug", "strategy", "response_mode"}


from typing import Union

def get_git_strategy() -> str:
    """Return the git strategy from config.yaml (falls back to agents.yaml for back-compat)."""
    return _APP_CONFIG.get("git_strategy", _AGENTS_CONFIG.get("git_strategy", "hybrid"))

def get_agent_strategy(agent_name: str) -> str:
    """Return the orchestrator strategy name for *agent_name* from agents.yaml."""
    return _AGENT_OVERRIDES.get(agent_name, {}).get("strategy", "autonomous")


def get_vector_config() -> dict:
    """Return vector index configuration from config.yaml with defaults."""
    cfg = _APP_CONFIG.get("vector_index", {})
    return {
        "embedding_model": cfg.get("embedding_model", "ollama/nomic-embed-text"),
        "embedding_fallback": cfg.get("embedding_fallback", "sentence-transformers/all-MiniLM-L6-v2"),
        "chunk_size": int(cfg.get("chunk_size", 500)),
        "chunk_overlap": int(cfg.get("chunk_overlap", 50)),
        "top_k": int(cfg.get("top_k", 10)),
    }

def get_agent_max_heartbeats(agent_name: str, default: int) -> Union[int, str]:
    """Return max_heartbeats configured for *agent_name* in agents.yaml (can be 'auto'), or *default*."""
    val = _AGENT_OVERRIDES.get(agent_name, {}).get("max_heartbeats", default)
    if val == "auto":
        return "auto"
    return int(val)


def get_agent_heartbeats_scale_factor(agent_name: str, default: float = 2.0) -> float:
    """Return heartbeats_scale_factor: per-agent override > config.yaml global > default."""
    global_scale = float(_APP_CONFIG.get("heartbeats_scale_factor", _AGENTS_CONFIG.get("heartbeats_scale_factor", default)))
    return float(_AGENT_OVERRIDES.get(agent_name, {}).get("heartbeats_scale_factor", global_scale))


def get_agent_debug(agent_name: str, default: bool = False) -> bool:
    """Return debug flag configured for *agent_name* in agents.yaml, or *default*."""
    return bool(_AGENT_OVERRIDES.get(agent_name, {}).get("debug", default))


def get_agent_response_mode(agent_name: str, default: str = "last") -> str:
    """Return response_mode for *agent_name*: per-agent override > config.yaml global > default."""
    global_mode = _APP_CONFIG.get("response_mode", _AGENTS_CONFIG.get("response_mode", default))
    return str(_AGENT_OVERRIDES.get(agent_name, {}).get("response_mode", global_mode))


def get_agent_model(agent_name: str, default: str | None = None) -> str:
    """Return the model configured for *agent_name* in agents.yaml, or *default*."""
    override = _AGENT_OVERRIDES.get(agent_name, {}).get("model")
    if override:
        return override
    return default if default is not None else DEFAULT_MODEL


def get_agent_llm_kwargs(agent_name: str) -> dict:
    """Return merged litellm kwargs for *agent_name*.

    Priority (highest first):
      1. Project-specific model_params (dynamically merged if session exists)
      2. Per-agent override in agents.yaml ``agents.<name>``
      3. Global ``llm_defaults`` in agents.yaml
      4. Hard-coded defaults above

    Non-litellm fields (model, max_heartbeats) are excluded.
    """
    merged = dict(_LLM_DEFAULTS)
    merged.update(_AGENT_OVERRIDES.get(agent_name, {}))

    try:
        from .tools import _PROJECT_SESSION
        if _PROJECT_SESSION and hasattr(_PROJECT_SESSION, "model_params") and _PROJECT_SESSION.model_params:
            merged.update(_PROJECT_SESSION.model_params)
    except Exception:
        pass

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

# Shared run logger — set by setup_debug_logging(), used by terminal.py debug_* funcs.
_RUN_LOGGER: "logging.Logger | None" = None


def get_run_logger():
    return _RUN_LOGGER


def setup_debug_logging():
    """Enable full debug logging for a run.

    - Creates a timestamped log file: ~/.opalacoder/logs/run_<timestamp>.log
    - Logs every litellm call (full prompt + response) via success/failure callbacks.
    - Enables workflow step logs (oracle outputs, worker starts/results) to the same file.
    - Sets OPALACODER_WORKFLOW_DEBUG=1 so terminal.py debug_* functions also fire.
    - Prints the log file path so the user knows where to look.
    """
    import litellm
    import logging
    from datetime import datetime

    global _RUN_LOGGER

    log_dir = os.path.join(os.path.expanduser("~"), ".opalacoder", "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"run_{timestamp}.log")

    logger = logging.getLogger(f"opalacoder.run.{timestamp}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)

    _RUN_LOGGER = logger

    # Enable workflow debug output in terminal.py (oracle + worker intermediate steps)
    os.environ["OPALACODER_WORKFLOW_DEBUG"] = "1"

    # litellm verbose → logs raw HTTP-level info to stderr; we capture structured data
    # ourselves via callbacks so we leave litellm's own verbose off to reduce noise.
    litellm.set_verbose = False

    SEP = "=" * 80

    def _llm_callback(kwargs, completion_response, start_time, end_time):
        messages = kwargs.get("messages", [])
        model = kwargs.get("model", "unknown")
        elapsed = (end_time - start_time).total_seconds() if start_time and end_time else 0

        lines = [
            f"\n{SEP}",
            f"[LLM CALL] model={model}  elapsed={elapsed:.2f}s",
            f"{SEP}",
            "--- MESSAGES (input) ---",
        ]
        for msg in messages:
            role = msg.get("role", "?").upper()
            content = msg.get("content") or ""
            # tool_calls in assistant messages
            tcs = msg.get("tool_calls")
            if tcs:
                content = f"<tool_calls> {tcs}"
            lines.append(f"\n[{role}]\n{content}")

        lines.append("\n--- RESPONSE (output) ---")
        if completion_response:
            try:
                choice = completion_response.choices[0]
                msg_out = choice.message
                if msg_out.content:
                    lines.append(msg_out.content)
                if getattr(msg_out, "tool_calls", None):
                    lines.append(f"<tool_calls> {msg_out.tool_calls}")
            except Exception:
                lines.append(str(completion_response))
        else:
            lines.append("(no response)")

        lines.append(SEP)
        logger.debug("\n".join(lines))

    litellm.success_callback = [_llm_callback]
    litellm.failure_callback = [_llm_callback]

    print(f"[debug] Full run log → {log_file}")
    return log_file


# Keep backward-compat alias used in older --debug path
def setup_litellm_debug():
    setup_debug_logging()

