"""Pushes the version-controlled phone-agent prompt up to ElevenLabs.

The outbound call agent's prompt is the thing that decides how SlotSaver sounds
on the phone, so it belongs in git and in review like any other source file -
not only inside a vendor dashboard where changes leave no trace.

    python scripts/sync_phone_agent.py            # push repo prompt -> ElevenLabs
    python scripts/sync_phone_agent.py --pull     # overwrite repo file from live

The prompt uses {{double_brace}} placeholders that ElevenLabs fills from the
dynamic variables place_call() sends; see app/services/call_service.py.
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "apps" / "api" / "app" / "agents" / "prompts" / "phone_agent.md"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pull", action="store_true", help="copy the live prompt into the repo")
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    agent_id = os.environ.get("ELEVENLABS_PHONE_AGENT_ID")
    if not api_key or not agent_id:
        sys.exit("ELEVENLABS_API_KEY and ELEVENLABS_PHONE_AGENT_ID must be set in .env")

    url = f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

    if args.pull:
        live = httpx.get(url, headers=headers, timeout=30.0)
        live.raise_for_status()
        prompt = live.json()["conversation_config"]["agent"]["prompt"]["prompt"]
        PROMPT_PATH.write_text(prompt + "\n", encoding="utf-8", newline="\n")
        print(f"pulled {len(prompt)} chars -> {PROMPT_PATH.relative_to(Path.cwd())}")
        return

    prompt = PROMPT_PATH.read_text(encoding="utf-8").rstrip("\n")
    resp = httpx.patch(
        url,
        headers=headers,
        json={"conversation_config": {"agent": {"prompt": {"prompt": prompt}}}},
        timeout=30.0,
    )
    resp.raise_for_status()
    pushed = resp.json()["conversation_config"]["agent"]["prompt"]["prompt"]
    print(f"pushed {len(prompt)} chars to {agent_id}")
    print("live prompt matches repo:", pushed.rstrip("\n") == prompt)


if __name__ == "__main__":
    main()
