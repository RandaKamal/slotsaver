"""Environment-backed configuration for the API.

Loads variables from the repo-root `.env` (python-dotenv walks up from the
current working directory to find it, so this works whether the server is
started from `apps/api` or the repo root). Never hardcode credentials here.

No telephony vars here by design: the MVP embeds the ElevenLabs agent
directly in the browser (mic -> agent -> our FastAPI tools). Twilio/PSTN
config can be added later without changing this shape.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = (
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_AGENT_ID",
    "BACKEND_BASE_URL",
)


@dataclass(frozen=True)
class Settings:
    elevenlabs_api_key: str | None
    elevenlabs_agent_id: str | None
    backend_base_url: str | None

    @property
    def missing_env_vars(self) -> list[str]:
        return [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]


def get_settings() -> Settings:
    return Settings(
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
        elevenlabs_agent_id=os.getenv("ELEVENLABS_AGENT_ID"),
        backend_base_url=os.getenv("BACKEND_BASE_URL"),
    )


settings = get_settings()
