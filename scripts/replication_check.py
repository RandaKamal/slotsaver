"""Run to run variance at a fixed ceiling.

An earlier sweep was interrupted, but it had already scored a set of items with
a seeded stratified sample. The relaunched sweep draws the SAME items with the
SAME seed, so the two runs are an independent replication of one another at no
extra API cost.

This matters for publication: evaluation reports that print a single accuracy
figure conceal how much of a model gap is run to run noise. Here the two runs
differ only in wall clock time, so any disagreement is API nondeterminism rather
than a change in the model, the prompt or the sample.

    python scripts/replication_check.py
"""

import glob
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "apps" / "api"))
from app.agents.naturalplan.scorer import mcnemar, wilson_interval  # noqa: E402

REPL = _ROOT / "results" / "replication"


def load(paths):
    recs = []
    for f in paths:
        blob = json.loads(Path(f).read_text(encoding="utf-8"))
        mt = blob.get("max_tokens")
        default = mt if isinstance(mt, int) else None
        for r in blob["records"]:
            if r.get("max_tokens") is None:
                r["max_tokens"] = default
            recs.append(r)
    return recs


def main() -> int:
    run_a = load(sorted(glob.glob(str(REPL / "*.json"))))
    run_b = load(sorted(glob.glob(str(_ROOT / "results" / "naturalplan_*.json"))))
    if not run_a or not run_b:
        print("need both a replication file and a main result file")
        return 1

    lines = ["| Model | Ceiling | Run A | Run B | Items | Agreement | McNemar p |",
             "|---|---|---|---|---|---|---|"]
    print(f"{'model':<10} {'ceil':>5} {'run A':>8} {'run B':>8} {'items':>6} "
          f"{'agree':>7} {'p':>8}")
    print("-" * 56)

    any_row = False
    for model in ("nemotron", "claude", "gemini"):
        for ceiling in sorted({r["max_tokens"] for r in run_a if r["model"] == model}):
            a = {r["example_id"]: r["solved"] for r in run_a
                 if r["model"] == model and r["max_tokens"] == ceiling}
            b = {r["example_id"]: r["solved"] for r in run_b
                 if r["model"] == model and r["max_tokens"] == ceiling}
            shared = sorted(set(a) & set(b))
            if len(shared) < 5:
                continue
            any_row = True
            av = [a[k] for k in shared]
            bv = [b[k] for k in shared]
            acc_a = sum(av) / len(av)
            acc_b = sum(bv) / len(bv)
            agree = sum(1 for x, y in zip(av, bv) if x == y) / len(shared)
            res = mcnemar(av, bv)
            p = res["p_value"]
            print(f"{model:<10} {ceiling:>5} {acc_a:>8.3f} {acc_b:>8.3f} "
                  f"{len(shared):>6} {agree:>7.3f} {p:>8.3f}")
            lines.append(f"| {model} | {ceiling} | {acc_a:.1%} | {acc_b:.1%} | "
                         f"{len(shared)} | {agree:.1%} | "
                         f"{'n.s.' if p >= 0.05 else f'{p:.4f}'} |")

    if not any_row:
        print("no overlapping (model, ceiling) pairs yet; rerun once the sweep finishes")
        return 0

    (_ROOT / "paper" / "table_replication.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")

    # Macros so the paper never quotes a replication number typed by hand.
    worst_agree, worst_model, n_pairs = 1.0, "", 0
    for model in ("nemotron", "claude", "gemini"):
        for ceiling in sorted({r["max_tokens"] for r in run_a if r["model"] == model}):
            a = {r["example_id"]: r["solved"] for r in run_a
                 if r["model"] == model and r["max_tokens"] == ceiling}
            b = {r["example_id"]: r["solved"] for r in run_b
                 if r["model"] == model and r["max_tokens"] == ceiling}
            shared = sorted(set(a) & set(b))
            if len(shared) < 5:
                continue
            n_pairs += 1
            agree = sum(1 for k in shared if a[k] == b[k]) / len(shared)
            if agree < worst_agree:
                worst_agree, worst_model = agree, model
    bs = chr(92)
    macros = {
        "replPairs": str(n_pairs),
        "replWorstAgree": f"{worst_agree * 100:.1f}" + bs + "%",
        "replWorstModel": worst_model,
    }
    (_ROOT / "paper" / "numbers_repl.tex").write_text(
        "\n".join(bs + "newcommand{" + bs + k + "}{" + v + "}"
                  for k, v in macros.items()) + "\n", encoding="utf-8")
    print(f"\nnumbers_repl.tex written (worst agreement {worst_agree:.1%} on {worst_model})")
    print("\nAgreement is the fraction of items scored identically in both runs.")
    print("A McNemar p above 0.05 means the two runs are not distinguishable,")
    print("which is the result we want: the measurement is stable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
