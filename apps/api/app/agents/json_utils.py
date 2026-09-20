import json
import re

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> dict:
    """Parses a model's raw text response as JSON.

    Three fallbacks, in order: the whole response as-is; the first complete
    JSON value even if the model appended more text after it (raw_decode
    stops at the end of that value instead of choking on the trailing
    "Extra data"); the first {...} block if the model wrapped it in prose or
    markdown fences before the opening brace.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        start = raw.find("{")
        if start != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(raw, start)
                return obj
            except json.JSONDecodeError:
                pass
        match = _JSON_BLOCK_RE.search(raw)
        if match:
            return json.loads(match.group(0))
        raise exc
