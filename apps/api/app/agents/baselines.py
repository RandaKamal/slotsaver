"""Competing rankers for RecoveryBench, all given the exact same prompt/contract as Nemotron
so the comparison is fair. Each function returns None if it can't run (e.g. missing API key)
instead of raising, so the benchmark can skip unavailable baselines cleanly."""

import os
import time

from app.agents.json_utils import extract_json_object
from app.agents.nemotron.client import call_nim_json
from app.agents.nemotron.prompts import RANKING_SYSTEM_PROMPT
from app.agents.nemotron.ranker import rank_candidates as _rank_with_nemotron

MISTRAL_NEMOTRON_MODEL = "mistralai/mistral-nemotron"  # open-source, free NIM endpoint
GEMINI_MODEL = "gemini-3.6-flash"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def _user_prompt(open_slot: dict, candidates: list[dict]) -> str:
    import json

    return json.dumps({"open_slot": open_slot, "candidates": candidates, "policies": {}})


def rank_with_nemotron(open_slot: dict, candidates: list[dict]) -> dict | None:
    start = time.perf_counter()
    result = _rank_with_nemotron(open_slot, candidates)
    result["_latency_seconds"] = time.perf_counter() - start
    return result


def rank_with_mistral_nemotron(open_slot: dict, candidates: list[dict]) -> dict | None:
    start = time.perf_counter()
    result = call_nim_json(MISTRAL_NEMOTRON_MODEL, RANKING_SYSTEM_PROMPT, _user_prompt(open_slot, candidates))
    result["_latency_seconds"] = time.perf_counter() - start
    return result


def rank_with_gemini(open_slot: dict, candidates: list[dict]) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    from google import genai

    client = genai.Client(api_key=api_key)
    start = time.perf_counter()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_user_prompt(open_slot, candidates),
        config={"system_instruction": RANKING_SYSTEM_PROMPT, "temperature": 0.2},
    )
    result = extract_json_object(response.text)
    result["_latency_seconds"] = time.perf_counter() - start
    return result


def rank_with_claude(open_slot: dict, candidates: list[dict]) -> dict | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    start = time.perf_counter()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        temperature=0.2,
        system=RANKING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(open_slot, candidates)}],
    )
    result = extract_json_object(message.content[0].text)
    result["_latency_seconds"] = time.perf_counter() - start
    return result


# Fast baselines: run every time, safe to hammer concurrently.
FAST_BASELINES = {
    "nemotron": rank_with_nemotron,
    "gemini": rank_with_gemini,
    "claude": rank_with_claude,
}

# Slow baselines: NVIDIA's free-tier capacity for this model serializes under concurrency
# (~40s/call, and 5 concurrent calls timed out entirely in testing). Opt-in only — don't
# run this on every iteration, only when building the final comparison numbers.
SLOW_BASELINES = {
    "mistral_nemotron": rank_with_mistral_nemotron,
}

BASELINES = {**FAST_BASELINES, **SLOW_BASELINES}
