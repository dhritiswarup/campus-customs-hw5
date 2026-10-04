"""Model, paths and limits for the Campus Customs agent team.

Every agent uses gpt-6-luna through Portkey. PORTKEY_API_KEY is read from the
nearest .env (HW5/ or the course root) and never logged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

BACKEND_DIR = Path(__file__).resolve().parent
HW5_DIR = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_CONFIG_PATH = HW5_DIR / ".mcp.json"
AUDIT_PATH = Path(os.getenv("CAMPUS_CUSTOMS_AUDIT") or HW5_DIR / "output" / "audit_trail.json")
ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"  # never written; source for resets
# Working copy the MCP server reads/writes. CAMPUS_CUSTOMS_DB points everything at a scratch copy.
WORKING_DB = Path(os.getenv("CAMPUS_CUSTOMS_DB") or HW5_DIR / "data" / "campus_customs_new.db")

for folder in (BACKEND_DIR, HW5_DIR, HW5_DIR.parent):
    load_dotenv(folder / ".env")

MODEL_NAME = "gpt-6-luna"  # the only model used anywhere in HW5
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# --- limits that keep token use in check -----------------------------------
MAX_DELEGATION_DEPTH = 3          # boss -> A -> B -> C, no deeper
MAX_DELEGATIONS_PER_RUN = 12      # across the whole team, per run
RUN_TOKEN_BUDGET = 600_000        # input + output tokens, whole team, per run
AGENT_REQUEST_LIMIT = 14          # model calls in one agent loop
AGENT_TOOL_CALL_LIMIT = 30        # tool calls in one agent loop
AGENT_TOKEN_LIMIT = 200_000       # tokens in one agent loop
AUDIT_CLIP_CHARS = 4_000          # longest tool result / text kept per audit field
MODEL_CALL_TIMEOUT_S = 60         # one model call; normal calls take 2-30 s, stalls are cut off and retried
MODEL_CALL_RETRIES = 4
RUN_TIMEOUT_S = 900               # wall clock for a whole team run


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to HW5/.env or the course-root .env.")
    return key


def build_model() -> OpenAIResponsesModel:
    key = require_api_key()
    client = AsyncOpenAI(
        api_key=key,
        base_url=PORTKEY_BASE_URL,
        timeout=MODEL_CALL_TIMEOUT_S,
        max_retries=MODEL_CALL_RETRIES,
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def load_prompt(file_name: str) -> str:
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8").strip()


def mcp_client_config(db_path: str | None = None) -> dict:
    """The campus-customs entry from .mcp.json, optionally pointed at another DB copy."""
    config = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    server = config["mcpServers"]["campus-customs"]
    # .mcp.json is portable ("python mcp_server/server.py" from the repo root). Launch it with this
    # interpreter (the project venv) and an absolute script path so it works from any folder.
    server["command"] = sys.executable
    server["args"] = [str((HW5_DIR / a).resolve()) if a.endswith(".py") else a for a in server.get("args", [])]
    db_path = db_path or os.getenv("CAMPUS_CUSTOMS_DB")  # stdio servers don't inherit env, so pass it on
    if db_path:
        server["env"] = {**server.get("env", {}), "CAMPUS_CUSTOMS_DB": str(Path(db_path).resolve())}
    return {"mcpServers": {"campus-customs": server}}
