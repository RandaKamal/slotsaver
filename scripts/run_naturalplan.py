"""Run NATURAL PLAN calendar scheduling across Nemotron / Claude / Gemini.

Benchmark: Zheng et al., "NATURAL PLAN: Benchmarking LLMs on Natural Language
Planning", arXiv:2406.04520. Data and evaluator: github.com/google-deepmind/
natural-plan (Apache-2.0 / CC-BY).

Why this benchmark: scoring is an exact match against a golden answer after a
regex parse. No human labels and no LLM judge, so the result does not depend on
who wrote the ground truth - which is the failure mode of our own RecoveryBench.

    python scripts/run_naturalplan.py --per-bucket 50 --shots 5
    python scripts/run_naturalplan.py --per-bucket 3 --models nemotron   # smoke

Every model receives the byte-identical prompt from the dataset. Results are
written to results/naturalplan_<timestamp>.json for the paper to cite.
"""

import argparse
import collections
import json
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "apps" / "api"))
load_dotenv(_ROOT / ".env")

from app.agents.naturalplan.runners import MODEL_IDS, RUNNERS  # noqa: E402
from app.agents.naturalplan.scorer import is_solved, wilson_interval  # noqa: E402

DATA_URL = (
    "https://raw.githubusercontent.com/google-deepmind/natural-plan/main/"
    "data/calendar_scheduling.json"
)
DATA_PATH = _ROOT / "data" / "calendar_scheduling.json"
RESULTS_DIR = _ROOT / "results"


def load_dataset() -> dict:
    if not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading NATURAL PLAN calendar data -> {DATA_PATH}")
        urllib.request.urlretrieve(DATA_URL, DATA_PATH)  # noqa: S310
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def stratified_sample(data: dict, per_bucket: int, seed: int) -> list[tuple[str, dict]]:
    """Equal N per participant-count bucket.

    The raw set is half 2-person cases, so a uniform random sample would mostly
    measure the easiest bucket and hide how models degrade with complexity.
    """
    buckets = collections.defaultdict(list)
    for key, item in data.items():
        buckets[str(item["num_people"])].append((key, item))
    rng = random.Random(seed)
    picked = []
    for bucket in sorted(buckets, key=int):
        items = sorted(buckets[bucket], key=lambda kv: kv[0])  # deterministic base order
        picked.extend(rng.sample(items, min(per_bucket, len(items))))
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-bucket", type=int, default=50, help="examples per participant count")
    ap.add_argument("--shots", type=int, choices=[0, 5], default=5)
    ap.add_argument("--models", nargs="+", default=list(RUNNERS), choices=list(RUNNERS))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--repeats", type=int, default=1, help="runs per example, for variance")
    # Same ceiling for every model. Nemotron reasons in the open and needs room
    # to finish; truncating it mid-thought would score a formatting artefact as
    # a planning failure. Output tokens are recorded so the cost of that room
    # shows up in the results rather than being hidden.
    ap.add_argument("--max-tokens", type=int, default=4096)
    args = ap.parse_args()

    data = load_dataset()
    sample = stratified_sample(data, args.per_bucket, args.seed)
    prompt_key = f"prompt_{args.shots}shot"
    print(
        f"{len(sample)} examples x {len(args.models)} models x {args.repeats} repeat(s) "
        f"= {len(sample) * len(args.models) * args.repeats} calls ({args.shots}-shot)\n"
    )

    jobs = [
        (model, key, item, rep)
        for model in args.models
        for key, item in sample
        for rep in range(args.repeats)
    ]
    records = []
    started = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(RUNNERS[m], it[prompt_key], args.max_tokens): (m, k, it, rep)
            for m, k, it, rep in jobs
        }
        for future in as_completed(futures):
            model, key, item, rep = futures[future]
            res = future.result()
            records.append(
                {
                    "model": model,
                    "example_id": key,
                    "repeat": rep,
                    "num_people": str(item["num_people"]),
                    "num_days": str(item["num_days"]),
                    "solved": bool(res.text) and is_solved(res.text, item["golden_plan"]),
                    "latency_s": round(res.latency_s, 3),
                    "input_tokens": res.input_tokens,
                    "output_tokens": res.output_tokens,
                    "error": res.error,
                    "response": res.text[:400],
                    "golden": item["golden_plan"],
                }
            )
            done += 1
            if done % 25 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} calls  ({time.time() - started:.0f}s)")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"naturalplan_{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "benchmark": "natural_plan_calendar_scheduling",
                "source": "arXiv:2406.04520 / github.com/google-deepmind/natural-plan",
                "shots": args.shots,
                "per_bucket": args.per_bucket,
                "seed": args.seed,
                "repeats": args.repeats,
                "model_ids": {m: MODEL_IDS[m] for m in args.models},
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summarise(records, args.models)
    print(f"\nwritten: {out.relative_to(_ROOT)}")


def summarise(records: list[dict], models: list[str]) -> None:
    print(f"\n{'model':<10} {'solve rate':>11} {'95% CI':>16} {'errors':>7} "
          f"{'med lat':>8} {'tok in':>8} {'tok out':>8}")
    print("-" * 74)
    for model in models:
        rows = [r for r in records if r["model"] == model]
        if not rows:
            continue
        ok = sum(r["solved"] for r in rows)
        errs = sum(bool(r["error"]) for r in rows)
        lats = sorted(r["latency_s"] for r in rows if not r["error"])
        med = lats[len(lats) // 2] if lats else 0.0
        lo, hi = wilson_interval(ok, len(rows))
        tin = sum(r["input_tokens"] for r in rows) // max(1, len(rows))
        tout = sum(r["output_tokens"] for r in rows) // max(1, len(rows))
        print(f"{model:<10} {ok:>4}/{len(rows):<6} {f'{lo:.3f}-{hi:.3f}':>16} "
              f"{errs:>7} {med:>7.2f}s {tin:>8} {tout:>8}")

    print(f"\nsolve rate by participant count:")
    people = sorted({r["num_people"] for r in records}, key=int)
    print(f"{'model':<10}" + "".join(f"{p + 'p':>9}" for p in people))
    print("-" * (10 + 9 * len(people)))
    for model in models:
        cells = []
        for p in people:
            rows = [r for r in records if r["model"] == model and r["num_people"] == p]
            cells.append(f"{sum(r['solved'] for r in rows) / len(rows):.3f}" if rows else "-")
        print(f"{model:<10}" + "".join(f"{c:>9}" for c in cells))


if __name__ == "__main__":
    main()
