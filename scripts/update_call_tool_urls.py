"""Repoints the five phone-call webhook tools at a new public base URL.

Run this whenever the base URL the tools should hit changes:

    # production, after deploying to App Platform
    python scripts/update_call_tool_urls.py https://<app>.ondigitalocean.app

    # local testing through a tunnel (a new URL on every cloudflared restart)
    python scripts/update_call_tool_urls.py https://<id>.trycloudflare.com

These tools are global to the ElevenLabs account, not per-environment: pointing
them at a tunnel takes production down, and pointing them at production stops
local call testing. Whoever ran it last wins, so say so in the team chat.

Only touches the *_call tools (webhooks, used for phone calls) - the plain
client tools the browser widget uses are executed in the page and are untouched.
"""

import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
import os  # noqa: E402

TOOL_IDS = {
    "get_available_slots_call": ("tool_1301m2yb2arne1ztf3jt0js6n6dj", "/api/voice/available-slots"),
    "save_scheduling_intent_call": ("tool_7201m2yb2x9xecpty0e8z17589m1", "/api/voice/preferences"),
    "book_appointment_call": ("tool_6301m2yb2xj7e1e8z5swnjwapkx0", "/api/voice/book"),
    "get_my_appointments_call": ("tool_9001m2ydz1nsfg9aeaw8m1qgwfyd", "/api/voice/my-appointments"),
    "cancel_appointment_call": ("tool_1501m2ydz1xye2svy6e07kj2gbhp", "/api/voice/cancel"),
}


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    base_url = sys.argv[1].rstrip("/")
    if not base_url.startswith("https://"):
        # ElevenLabs will accept the PATCH and then fail every tool call at
        # run time, which surfaces as the agent going quiet mid-conversation.
        raise SystemExit(f"refusing to set a non-HTTPS webhook URL: {base_url}")
    key = os.environ["ELEVENLABS_API_KEY"]
    headers = {"xi-api-key": key, "Content-Type": "application/json"}

    for name, (tool_id, path) in TOOL_IDS.items():
        current = httpx.get(
            f"https://api.elevenlabs.io/v1/convai/tools/{tool_id}", headers=headers
        ).json()
        schema = current["tool_config"]["api_schema"]
        schema["url"] = base_url + path
        resp = httpx.patch(
            f"https://api.elevenlabs.io/v1/convai/tools/{tool_id}",
            headers=headers,
            json={"tool_config": {**current["tool_config"], "api_schema": schema}},
        )
        resp.raise_for_status()
        print(f"  {name} -> {schema['url']}")

    print("\nDone. These webhook tools now point at your tunnel.")
    print("Make sure your API server is actually running and reachable through it.")


if __name__ == "__main__":
    main()
