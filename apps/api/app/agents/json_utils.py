import json
import re

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> dict:
    """Parses a model's raw text response as JSON, falling back to extracting the first
    {...} block if the model wrapped it in prose or markdown fences."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(raw)
        if match:
            return json.loads(match.group(0))
        raise
