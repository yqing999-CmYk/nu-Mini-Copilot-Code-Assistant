import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# claude-haiku-4-5 for fast inline responses; sonnet for deeper analysis
FAST_MODEL: str = os.environ.get("CODEASSIST_FAST_MODEL", "claude-haiku-4-5-20251001")
SMART_MODEL: str = os.environ.get("CODEASSIST_SMART_MODEL", "claude-sonnet-4-6")


def require_api_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Copy .env.example to .env and add your key."
        )
    return ANTHROPIC_API_KEY
