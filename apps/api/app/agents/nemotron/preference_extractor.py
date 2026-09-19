import json

from app.agents.nemotron.client import call_nemotron_json
from app.agents.nemotron.prompts import EXTRACTION_SYSTEM_PROMPT


def extract_preferences(transcript: str, patient_id: str) -> dict:
    user_prompt = json.dumps({"patient_id": patient_id, "transcript": transcript})
    return call_nemotron_json(EXTRACTION_SYSTEM_PROMPT, user_prompt)


if __name__ == "__main__":
    result = extract_preferences(
        transcript=(
            "Book me Friday at 2, but if anything earlier opens this week, afternoons are "
            "best, not Tuesday, and I prefer Sarah but anyone is okay."
        ),
        patient_id="patient_1",
    )
    print(json.dumps(result, indent=2))
