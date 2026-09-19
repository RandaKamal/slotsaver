"""RecoveryBench core logic: runs every available model baseline against FIFO on hand-labeled
scenarios, in parallel (all case x baseline calls fire concurrently via a thread pool — these
are I/O-bound network calls, so this is a straightforward ~Nx speedup with N total calls).

Shared by scripts/run_benchmark.py and the /api/benchmark/run playground endpoint.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.agents.baselines import BASELINES, FAST_BASELINES, SLOW_BASELINES

FIXTURES_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "benchmark_cases.json"
)


def fifo_baseline(candidates: list[dict]) -> str:
    """Naive baseline: always contact whoever is first in the list, ignoring preferences."""
    return candidates[0]["patient_id"]


def run_benchmark(max_workers: int = 12, include_slow: bool = False) -> dict:
    """include_slow=True also runs mistral_nemotron, which serializes under NVIDIA's free-tier
    concurrency limits (~40s/case, run sequentially) — off by default so the benchmark stays
    fast enough to re-run during iteration. Turn it on only for the final comparison numbers."""
    cases = json.loads(FIXTURES_PATH.read_text())
    baselines = {**FAST_BASELINES, **(SLOW_BASELINES if include_slow else {})}

    # Flatten every (case, baseline) pair into one task list so everything runs concurrently,
    # not just parallel-per-case or parallel-per-baseline.
    tasks: dict[tuple, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for case in cases:
            for name, fn in baselines.items():
                future = pool.submit(fn, case["open_slot"], case["candidates"])
                futures[future] = (case["case_id"], name)

        for future in as_completed(futures):
            case_id, baseline_name = futures[future]
            try:
                tasks[(case_id, baseline_name)] = future.result()
            except Exception as exc:  # noqa: BLE001 — record the failure, don't kill the run
                tasks[(case_id, baseline_name)] = {"_error": str(exc)}

    results = []
    for case in cases:
        row = {
            "case_id": case["case_id"],
            "notes": case.get("notes"),
            "ground_truth": case["ground_truth_best_id"],
            "picks": {},
        }
        row["picks"]["fifo"] = {
            "pick": fifo_baseline(case["candidates"]),
            "correct": fifo_baseline(case["candidates"]) == case["ground_truth_best_id"],
            "latency_seconds": 0.0,
            "reason": "always contacts whoever is first in the list",
        }
        for name in BASELINES:
            outcome = tasks.get((case["case_id"], name))
            if outcome is None:
                row["picks"][name] = {"pick": None, "correct": False, "skipped": True}
                continue
            if "_error" in outcome:
                row["picks"][name] = {"pick": None, "correct": False, "error": outcome["_error"]}
                continue
            pick = outcome["ranked_candidate_ids"][0]
            reason = next(
                (c["reason"] for c in outcome["candidates"] if c["patient_id"] == pick),
                None,
            )
            row["picks"][name] = {
                "pick": pick,
                "correct": pick == case["ground_truth_best_id"],
                "latency_seconds": round(outcome.get("_latency_seconds", 0.0), 2),
                "reason": reason,
            }
        results.append(row)

    baseline_names = ["fifo", *BASELINES.keys()]
    accuracy = {}
    for name in baseline_names:
        attempted = [r["picks"][name] for r in results if not r["picks"][name].get("skipped")]
        if not attempted:
            accuracy[name] = None
            continue
        accuracy[name] = sum(p["correct"] for p in attempted) / len(attempted)

    return {
        "cases": results,
        "total": len(results),
        "accuracy": accuracy,
    }
