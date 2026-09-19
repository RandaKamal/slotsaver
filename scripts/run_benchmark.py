"""Owner: Kevin. RecoveryBench — Nemotron vs FIFO vs Mistral-Nemotron vs Gemini vs Claude.

Loads hand-labeled synthetic scenarios from apps/api/tests/fixtures/benchmark_cases.json and
runs every available baseline concurrently (see apps/api/app/agents/benchmark.py). Gemini and
Claude are skipped automatically if GEMINI_API_KEY / ANTHROPIC_API_KEY aren't set in .env.
Every result is a real API call — no fabricated numbers.

Usage (from repo root, with keys set in .env):
    python scripts/run_benchmark.py              # fast baselines only (nemotron, gemini, claude)
    python scripts/run_benchmark.py --include-slow  # also runs mistral_nemotron (~40s/case,
                                                      # NVIDIA free-tier serializes it)
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.agents.benchmark import run_benchmark  # noqa: E402


def main() -> None:
    include_slow = "--include-slow" in sys.argv
    result = run_benchmark(include_slow=include_slow)
    baseline_names = list(result["accuracy"].keys())

    header = f"{'case_id':<40}" + "".join(f"{name:<18}" for name in baseline_names)
    print(header)
    print("-" * len(header))
    for row in result["cases"]:
        line = f"{row['case_id']:<40}"
        for name in baseline_names:
            p = row["picks"][name]
            mark = "skip" if p.get("skipped") else ("OK" if p["correct"] else "x")
            line += f"{(p.get('pick') or '-') + ' ' + mark:<18}"
        print(line)

    print("-" * len(header))
    for name in baseline_names:
        acc = result["accuracy"][name]
        acc_str = "n/a (skipped)" if acc is None else f"{acc:.0%}"
        print(f"{name:<20} top-1 accuracy: {acc_str}")


if __name__ == "__main__":
    main()
