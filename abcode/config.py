"""Global configuration defaults for ABCode."""

import os
from dotenv import load_dotenv

load_dotenv()

# Model used for all agents (can be overridden via CLI --model)
DEFAULT_MODEL = os.getenv("ABCODE_MODEL", "ollama/mistral-nemo")

# Maximum retry attempts for a failing subplan step
DEFAULT_MAX_RETRIES = 3

# MemGPT heartbeat budget per planning turn
DEFAULT_MAX_HEARTBEATS = 15

# SQLite database file for session persistence
DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".abcode", "sessions.db"
)

# Execution mode: "auto" | "plan" | "edit"
DEFAULT_MODE = "plan"

# Sensitive operations that require user approval in "edit" mode
SENSITIVE_OPS = {
    "write_file", "delete_file", "run_shell",
    "send_network_request", "create_user", "delete_user",
}
