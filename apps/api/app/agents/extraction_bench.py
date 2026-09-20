"""A/B harness: does the self-critique pass actually improve extraction?

This measures ONE thing - single-pass vs two-pass on identical cases with
identical labels. That comparison is fair even though the labels are
hand-written, because label bias lands on both arms equally. It is NOT a
cross-model claim; see docs/benchmark.md for why that one is weaker.

Graded per assertion, not per case: a case asserting four fields contributes
four data points, so a near-miss is visible instead of being rounded to zero.
"""

import datetime
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.agents.nemotron.preference_extractor import (
    diff_extractions,
    extract_preferences,
    refine_preferences,
)

CASES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "extraction_cases.json"


def _dig(obj: Any, dotted: str) -> Any:
    """Resolves 'soft_preferences.preferred_provider' against a nested dict."""
    for part in dotted.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        return sorted(map(str, actual)) == sorted(map(str, expected))
    if isinstance(expected, str) and isinstance(actual, str):
        return actual.strip().lower() == expected.strip().lower()
    return actual == expected


def _grade(extraction: dict, expect: dict) -> list[dict]:
    return [
        {
            "field": field,
            "expected": want,
            "actual": _dig(extraction, field),
            "pass": _matches(_dig(extraction, field), want),
        }
        for field, want in expect.items()
    ]


def _run_case(case: dict, today: datetime.date) -> dict:
    ctx = case.get("context")
    draft = extract_preferences(case["transcript"], "bench", context=ctx, today=today)
    revised = refine_preferences(case["transcript"], draft, context=ctx, today=today)
    return {
        "id": case["id"],
        "note": case.get("note"),
        "single_pass": _grade(draft, case["expect"]),
        "two_pass": _grade(revised, case["expect"]),
        "critique_changed": diff_extractions(draft, revised),
    }


def run_extraction_bench(max_workers: int = 3) -> dict:
    spec = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    today = datetime.date.fromisoformat(spec["today"])
    cases = spec["cases"]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(lambda c: _run_case(c, today), cases))

    def score(arm: str) -> dict:
        checks = [c for r in results for c in r[arm]]
        passed = sum(1 for c in checks if c["pass"])
        return {"passed": passed, "total": len(checks), "accuracy": round(passed / len(checks), 3)}

    single, two = score("single_pass"), score("two_pass")
    return {
        "cases": results,
        "single_pass": single,
        "two_pass": two,
        "delta": round(two["accuracy"] - single["accuracy"], 3),
        "cases_critique_touched": sum(1 for r in results if r["critique_changed"]),
    }
