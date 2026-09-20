"""Nemotron-backed extraction of scheduling INTENT from what a patient said.

Two entry points, deliberately separated by latency budget:

- extract_preferences()  - one NIM call. Used where a human is waiting.
- refine_preferences()   - a second critique pass over a draft. Roughly doubles
  the work, so it is only ever called off the request path (see the background
  task in app/services/preference_service.py). Nothing a caller waits on should
  invoke it directly.
"""

import copy
import datetime
import json

from app.agents.nemotron.client import call_nemotron_json
from app.agents.nemotron.prompts import CRITIQUE_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT

def _dated(prompt: str, today: datetime.date | None) -> str:
    today = today or datetime.date.today()
    return prompt.format(today=today.isoformat(), weekday=today.strftime("%A"))


def extract_preferences(
    transcript: str,
    patient_id: str,
    context: str | None = None,
    today: datetime.date | None = None,
) -> dict:
    """Single-pass extraction.

    `context` carries earlier conversation the patient's final sentence depends
    on. Without it a request like "only Mondays at 6" loses the provider they
    named three turns earlier.
    """
    payload = {"patient_id": patient_id, "transcript": transcript}
    if context:
        payload["earlier_conversation"] = context
    return call_nemotron_json(
        _dated(EXTRACTION_SYSTEM_PROMPT, today), json.dumps(payload)
    )


def _set_path(target: dict, dotted: str, value) -> bool:
    """Writes a dotted path into a nested dict. False if the path doesn't exist.

    Refusing to create new keys is deliberate: the critique may only correct
    fields the schema already defines, never invent structure.
    """
    parts = dotted.split(".")
    node = target
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return False
    if parts[-1] not in node:
        return False
    node[parts[-1]] = value
    return True


def refine_preferences(
    transcript: str,
    draft: dict,
    context: str | None = None,
    today: datetime.date | None = None,
) -> dict:
    """Second pass: ask the model only what the draft got wrong, then patch it.

    An earlier version had the critique rewrite the whole object; it corrupted a
    list it was not even asked about (dropped Sunday, duplicated Saturday). So
    it now returns targeted corrections which are merged field by field, and
    anything malformed or off-schema is dropped. The draft is the floor: a bad
    critique can never make the result worse than no critique.
    """
    payload = {"transcript": transcript, "draft_extraction": draft}
    if context:
        payload["earlier_conversation"] = context
    try:
        response = call_nemotron_json(
            _dated(CRITIQUE_SYSTEM_PROMPT, today), json.dumps(payload)
        )
    except Exception:
        return draft

    corrections = response.get("corrections") if isinstance(response, dict) else None
    if not isinstance(corrections, dict) or not corrections:
        return draft

    revised = copy.deepcopy(draft)
    for path, value in corrections.items():
        _set_path(revised, path, value)
    return revised


def diff_extractions(draft: dict, revised: dict) -> dict[str, dict]:
    """Field-level changes the critique pass made. Used for logging and the harness."""
    changes: dict[str, dict] = {}
    for key in sorted(set(draft) | set(revised)):
        before, after = draft.get(key), revised.get(key)
        if before != after:
            changes[key] = {"before": before, "after": after}
    return changes
