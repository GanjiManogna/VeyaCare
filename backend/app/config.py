
import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve backend/.env independently of the shell's current directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
APP_ENV = os.getenv("APP_ENV", "development")


def validate_api_keys():
    """Check whether the required API credentials are configured."""

    missing = []

    if not GOOGLE_API_KEY:
        missing.append("GOOGLE_API_KEY")

    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")

    if not ELEVENLABS_VOICE_ID:
        missing.append("ELEVENLABS_VOICE_ID")

    if missing:
        raise ValueError(
            "Missing configuration: " + ", ".join(missing)
        )

    return True
