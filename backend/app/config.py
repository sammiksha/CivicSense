import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", BASE / "data"))
MARKET_DIR = DATA_DIR / "market"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
FRONTEND_DIR = BASE / "frontend"
DB_PATH = os.getenv("DB_PATH", str(BASE / "structuraai.db"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MC_PATHS = int(os.getenv("MC_PATHS", "10000"))
MC_SEED = int(os.getenv("MC_SEED", "42"))
LIVE_DATA = os.getenv("STRUCTURAAI_LIVE_DATA", "0") == "1"

ENGINE_VERSION = "engine-0.1"


def model_version() -> str:
    return f"{ANTHROPIC_MODEL if ANTHROPIC_API_KEY else 'offline'}|rules-v1|{ENGINE_VERSION}"


def load_rules() -> dict:
    return json.loads((DATA_DIR / "config" / "rules.json").read_text())
