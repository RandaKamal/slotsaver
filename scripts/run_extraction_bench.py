"""Runs the single-pass vs two-pass extraction A/B and prints a table.

    python scripts/run_extraction_bench.py
"""

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

import json  # noqa: E402

from app.agents.extraction_bench import run_extraction_bench  # noqa: E402


def main() -> None:
    result = run_extraction_bench()
    print(f"\n{'case':<28} {'1-pass':>8} {'2-pass':>8}  critique changed")
    print("-" * 72)
    for case in result["cases"]:
        one = sum(c["pass"] for c in case["single_pass"])
        two = sum(c["pass"] for c in case["two_pass"])
        total = len(case["single_pass"])
        changed = ",".join(case["critique_changed"]) or "-"
        print(f"{case['id']:<28} {one}/{total:<6} {two}/{total:<6}  {changed[:28]}")
    print("-" * 72)
    s, t = result["single_pass"], result["two_pass"]
    print(f"{'ACCURACY':<28} {s['accuracy']:>8} {t['accuracy']:>8}  delta {result['delta']:+}")
    print(f"\ncritique touched {result['cases_critique_touched']} of {len(result['cases'])} cases")
    print("NOTE: 1 assertion = 0.043. Two runs cannot separate a real effect from noise.")
    print(json.dumps({"single_pass": s, "two_pass": t}, indent=1))


if __name__ == "__main__":
    main()
