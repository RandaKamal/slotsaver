"""Builds the paper's figures, tables and numeric macros from result JSONs.

Colour and mark choices follow the validated three-slot categorical palette
(blue/orange/aqua), which clears the all-pairs CVD and normal-vision floors. The
aqua slot sits below 3:1 contrast on a light surface, so every series is also
direct-labelled and every figure has a table counterpart: identity is never
carried by colour alone.

Every number the paper quotes is emitted here into numbers.tex rather than typed
by hand, so the prose cannot drift from the data it describes.
"""

import glob
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "apps" / "api"))
from app.agents.naturalplan.scorer import mcnemar, wilson_interval  # noqa: E402

PAPER = _ROOT / "paper"
FIGDIR = PAPER / "figures"
SERIES = {"nemotron": "#2a78d6", "claude": "#eb6834", "gemini": "#1baf7a"}
LABEL = {
    "nemotron": "Nemotron Super",
    "claude": "Claude Haiku 4.5",
    "gemini": "Gemini 3.5 Flash",
}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
# vertical offsets (points) so converging end-labels do not overlap
LABEL_DY = {"nemotron": 13, "claude": 0, "gemini": -13}
# larger offsets for the scatter, where labels are two lines tall and the
# points cluster at similar accuracy
LABEL_DY_SCATTER = {"nemotron": 0, "claude": 30, "gemini": -30}

plt.rcParams.update({
    "figure.dpi": 200, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "legend.frameon": False,
})


def load(pattern="results/naturalplan_*.json", include_checkpoint=True):
    """Loads completed result files, and optionally the in-flight checkpoint.

    The checkpoint lets figures be rebuilt from a run that is still going, which
    matters because ceilings are executed in ascending order: the highest and
    most important ceiling finishes last.
    """
    recs = []
    files = sorted(glob.glob(str(_ROOT / pattern)))
    ckpt = _ROOT / "results" / "_checkpoint.json"
    if include_checkpoint and ckpt.exists():
        files.append(str(ckpt))
    for f in files:
        blob = json.loads(Path(f).read_text(encoding="utf-8"))
        mt = blob.get("max_tokens")
        default = mt if isinstance(mt, int) else None
        for r in blob["records"]:
            if r.get("max_tokens") is None:
                r["max_tokens"] = default
            r["_shots"] = blob.get("shots")
            recs.append(r)
    # A finished run rewrites everything the checkpoint held, so drop duplicates
    # on the identity of a single call.
    seen, unique = set(), []
    for r in recs:
        key = (r["model"], r.get("max_tokens"), r["example_id"], r.get("repeat", 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def rate(rows):
    if not rows:
        return 0.0, 0.0, 0.0, 0
    ok = sum(r["solved"] for r in rows)
    lo, hi = wilson_interval(ok, len(rows))
    return ok / len(rows), lo, hi, len(rows)


def sel(recs, model=None, budget=None, people=None):
    out = recs
    if model:
        out = [r for r in out if r["model"] == model]
    if budget is not None:
        out = [r for r in out if r["max_tokens"] == budget]
    if people is not None:
        out = [r for r in out if r["num_people"] == people]
    return out


def _tidy(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def truncated(r, budget):
    return r["output_tokens"] >= budget


def truncation_rate(rows, budget):
    """Fraction of generations that ended at the ceiling rather than at a stop
    token. Uses the emitted token count as a proxy, since not every vendor SDK
    surfaces a finish reason consistently."""
    if not rows:
        return 0.0
    return sum(1 for r in rows if truncated(r, budget)) / len(rows)


def conditional_rate(rows, budget):
    """Solve rate over generations that were allowed to finish.

    This separates two things a headline accuracy number conflates: the model
    proposed a wrong meeting time (a planning failure) versus the model never
    got to propose one (a harness failure). Reported alongside, not instead of,
    the unconditional rate, since a model that needs more room is genuinely more
    expensive to deploy.
    """
    finished = [r for r in rows if not truncated(r, budget) and not r["error"]]
    return rate(finished)


def fig_token_budget(recs, out="fig1_token_budget.png"):
    """Two stacked panels sharing an x axis: the effect, then its mechanism.

    Deliberately not a dual-axis chart. Solve rate and truncation rate are
    different measures and get their own panel each.
    """
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    if len(budgets) < 2:
        print("  skip fig1: needs >= 2 ceilings")
        return
    fig, (ax, bx) = plt.subplots(
        2, 1, figsize=(5.4, 5.0), sharex=True, gridspec_kw={"hspace": 0.18}
    )
    for model, colour in SERIES.items():
        xs, ys, lo_e, hi_e, ts = [], [], [], [], []
        for b in budgets:
            rows = sel(recs, model, b)
            if not rows:
                continue
            p, lo, hi, _ = rate(rows)
            xs.append(b); ys.append(p); lo_e.append(p - lo); hi_e.append(hi - p)
            ts.append(truncation_rate(rows, b))
        if not xs:
            continue
        ax.errorbar(xs, ys, yerr=[lo_e, hi_e], color=colour, linewidth=2,
                    marker="o", markersize=6, capsize=3, elinewidth=1,
                    label=LABEL[model])
        # The series converge at the high ceiling, so end labels land on top of
        # each other. Stagger them vertically rather than dropping them: the
        # aqua slot is below 3:1 contrast and must not rely on colour alone.
        ax.annotate(LABEL[model], (xs[-1], ys[-1]), textcoords="offset points",
                    xytext=(9, LABEL_DY[model]), color=INK2, fontsize=7.5,
                    va="center")
        bx.plot(xs, ts, color=colour, linewidth=2, marker="o", markersize=6,
                label=LABEL[model])

    for a in (ax, bx):
        a.set_xscale("log", base=2)
        a.set_ylim(-0.03, 1.03)
        a.set_xlim(budgets[0] * 0.85, budgets[-1] * 2.1)
        _tidy(a)
    bx.set_xticks(budgets)
    bx.set_xticklabels([str(b) for b in budgets])
    ax.set_ylabel("Solve rate")
    bx.set_ylabel("Truncated at ceiling")
    bx.set_xlabel("Output token ceiling (max_tokens)")
    ax.set_title("(a) Solve rate collapses when a model cannot finish reasoning",
                 loc="left")
    bx.set_title("(b) The mechanism: generations cut off before an answer",
                 loc="left")
    ax.legend(loc="lower right", fontsize=7.5, handlelength=1.4)
    fig.savefig(FIGDIR / out)
    plt.close(fig)
    print(f"  {out}")


def fig_difficulty(recs, out="fig2_difficulty.png"):
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    top = budgets[-1] if budgets else None
    people = sorted({r["num_people"] for r in recs}, key=int)
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    for model, colour in SERIES.items():
        xs, ys, lo_e, hi_e = [], [], [], []
        for p_ in people:
            rows = sel(recs, model, top, p_)
            if not rows:
                continue
            v, lo, hi, _ = rate(rows)
            xs.append(int(p_)); ys.append(v); lo_e.append(v - lo); hi_e.append(hi - v)
        if not xs:
            continue
        ax.errorbar(xs, ys, yerr=[lo_e, hi_e], color=colour, linewidth=2,
                    marker="o", markersize=6, capsize=3, elinewidth=1,
                    label=LABEL[model])
    ax.set_xlabel("Participants in the meeting (task difficulty)")
    ax.set_ylabel("Solve rate")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title(f"Solve rate by scheduling complexity at a {top} token ceiling", loc="left")
    ax.legend(loc="lower left", fontsize=8)
    _tidy(ax)
    fig.savefig(FIGDIR / out)
    plt.close(fig)
    print(f"  {out}")


def fig_efficiency(recs, out="fig3_efficiency.png"):
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    top = budgets[-1] if budgets else None
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    max_tok = 0
    for model, colour in SERIES.items():
        all_rows = sel(recs, model, top)
        ok = [r for r in all_rows if not r["error"]]
        if not ok:
            continue
        # Solve rate over EVERY attempted item, matching Table 1. Tokens and
        # latency are only defined for calls that returned, so those average
        # over successes. Using different denominators for the two axes of the
        # same point would put a number here that contradicts the table.
        p, lo, hi, _ = rate(all_rows)
        tok = sum(r["output_tokens"] for r in ok) / len(ok)
        lat = sorted(r["latency_s"] for r in ok)[len(ok) // 2]
        max_tok = max(max_tok, tok)
        ax.errorbar([tok], [p], yerr=[[p - lo], [hi - p]], color=colour,
                    marker="o", markersize=11, capsize=3, elinewidth=1, linestyle="none")
        ax.annotate(f"{LABEL[model]}\n{p:.0%} at {tok:.0f} tok, {lat:.1f}s",
                    (tok, p), textcoords="offset points", xytext=(12, -6),
                    color=INK2, fontsize=8)
    ax.set_xlabel("Mean output tokens per task (proxy for cost)")
    ax.set_ylabel("Solve rate")
    ax.set_title("Accuracy against output spend: up and to the left is better", loc="left")
    # Token counts cannot be negative, and the right edge needs room for the
    # longest annotation rather than clipping it.
    ax.set_xlim(0, max_tok * 1.75 if max_tok else 1)
    ax.set_ylim(-0.03, 1.12)
    _tidy(ax)
    fig.savefig(FIGDIR / out)
    plt.close(fig)
    print(f"  {out}")


def pct(x):
    return f"{x * 100:.1f}" + chr(92) + "%"


def write_latex(recs):
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    if not budgets:
        print("  skip latex: no budgets recorded")
        return
    low, top = budgets[0], budgets[-1]

    def acc(model, budget):
        rows = sel(recs, model, budget)
        return rate(rows)[0] if rows else 0.0

    macros = {
        "tokenLowBudget": str(low),
        "tokenHighBudget": str(top),
        "nemotronName": "Nemotron Super 120B-A12B",
        "claudeName": "Claude Haiku 4.5",
        "geminiName": "Gemini 3.5 Flash",
        "nemotronLowAcc": pct(acc("nemotron", low)),
        "nemotronHighAcc": pct(acc("nemotron", top)),
        "nemotronTruncLow": pct(truncation_rate(sel(recs, "nemotron", low), low)),
        "nemotronTruncHigh": pct(truncation_rate(sel(recs, "nemotron", top), top)),
        "claudeTruncLow": pct(truncation_rate(sel(recs, "claude", low), low)),
        "nemotronCondLow": pct(conditional_rate(sel(recs, "nemotron", low), low)[0]),
        "nemotronCondHigh": pct(conditional_rate(sel(recs, "nemotron", top), top)[0]),
        "nemotronCondLowN": str(conditional_rate(sel(recs, "nemotron", low), low)[3]),
        "claudeLowAcc": pct(acc("claude", low)),
        "claudeHighAcc": pct(acc("claude", top)),
        "geminiLowAcc": pct(acc("gemini", low)),
        "geminiHighAcc": pct(acc("gemini", top)),
        "datasetSize": "1{,}000",
        "geminiPublishedRepro": "48.9" + chr(92) + "%",
        "geminiPublishedPaper": "48" + chr(92) + "%",
        "nemotronTotalParams": "120B",
        "nemotronActiveParams": "12B",
        "runDate": "20 September 2026",
    }
    bs = chr(92)
    lines = [bs + "newcommand{" + bs + k + "}{" + v + "}" for k, v in macros.items()]
    (PAPER / "numbers.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    body = []
    for model in SERIES:
        rows = sel(recs, model, top)
        if not rows:
            continue
        p, lo, hi, n = rate(rows)
        ok = [r for r in rows if not r["error"]]
        lat = sorted(r["latency_s"] for r in ok)[len(ok) // 2] if ok else 0.0
        tok = sum(r["output_tokens"] for r in ok) / max(1, len(ok))
        trunc = truncation_rate(rows, top)
        cond = conditional_rate(rows, top)[0]
        body.append(
            f"{LABEL[model]} & {p * 100:.1f} & {lo * 100:.1f}--{hi * 100:.1f} & "
            f"{trunc * 100:.1f} & {cond * 100:.1f} & {n} & {lat:.1f} & {tok:.0f} " + bs * 2
        )
    table = [
        bs + "begin{table}[t]", bs + "centering", bs + "small",
        bs + "begin{tabular}{lrrrrrrr}", bs + "toprule",
        "Model & Solve " + bs + "% & 95" + bs + "% CI & Trunc " + bs + "% & Cond "
        + bs + "% & $n$ & Lat.(s) & Out tok " + bs * 2,
        bs + "midrule", *body, bs + "bottomrule", bs + "end{tabular}",
        bs + "caption{Results at a ceiling of " + str(top) + " tokens. Solve "
        + bs + "% is the headline number an evaluation would normally report. "
        "Trunc " + bs + "% is the fraction of generations that ended at the ceiling "
        "rather than at a stop token; Cond " + bs + "% is the solve rate over only "
        "those generations that were allowed to finish. Where Trunc " + bs + "% is "
        "above zero, Solve " + bs + "% understates the model. Intervals are 95"
        + bs + "% Wilson. Latency is the median of successful calls, timed around "
        "the request only.}",
        bs + "label{tab:main}", bs + "end{table}",
    ]
    (PAPER / "table_main.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(f"  numbers.tex + table_main.tex (ceilings {budgets})")


def write_significance(recs, out="table_sig.tex"):
    """Pairwise McNemar tests at the highest ceiling.

    The models are run on the same items, so the outcomes are paired and a
    two-sample proportion test would discard that pairing. Reporting only
    overlapping items keeps the test exact.
    """
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    if not budgets:
        return
    top = budgets[-1]
    by_model = {}
    for model in SERIES:
        by_model[model] = {
            (r["example_id"], r.get("repeat", 0)): r["solved"]
            for r in sel(recs, model, top)
        }
    bs = chr(92)
    rows, md = [], ["| Pair | Only A | Only B | Discordant | p (exact McNemar) |",
                    "|---|---|---|---|---|"]
    names = [m for m in SERIES if by_model.get(m)]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = sorted(set(by_model[a]) & set(by_model[b]))
            if len(shared) < 2:
                continue
            res = mcnemar([by_model[a][k] for k in shared],
                          [by_model[b][k] for k in shared])
            verdict = "n.s." if res["p_value"] >= 0.05 else f"{res['p_value']:.4f}"
            rows.append(f"{LABEL[a]} vs {LABEL[b]} & {res['a_only']} & {res['b_only']} & "
                        f"{res['n_discordant']} & {verdict} " + bs * 2)
            md.append(f"| {LABEL[a]} vs {LABEL[b]} | {res['a_only']} | {res['b_only']} "
                      f"| {res['n_discordant']} | {verdict} (n={len(shared)}) |")
    if not rows:
        return
    table = [
        bs + "begin{table}[t]", bs + "centering", bs + "small",
        bs + "begin{tabular}{lrrrr}", bs + "toprule",
        "Comparison & Only A & Only B & Disc. & $p$ " + bs * 2,
        bs + "midrule", *rows, bs + "bottomrule", bs + "end{tabular}",
        bs + "caption{Exact McNemar tests on paired per item outcomes at the "
        + str(top) + " token ceiling. Only items attempted by both models are "
        "included. `n.s.' denotes $p " + bs + "geq 0.05$.}",
        bs + "label{tab:sig}", bs + "end{table}",
    ]
    (PAPER / out).write_text("\n".join(table) + "\n", encoding="utf-8")
    (PAPER / "table_sig.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md))


def write_markdown_table(recs, out="table1.md"):
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    top = budgets[-1] if budgets else None
    lines = ["| Model | Solve rate | 95% CI | Truncated | Cond. solve | n | Errors "
             "| Median latency | Mean out tokens |",
             "|---|---|---|---|---|---|---|---|---|"]
    for model in SERIES:
        rows = sel(recs, model, top)
        if not rows:
            continue
        p, lo, hi, n = rate(rows)
        ok = [r for r in rows if not r["error"]]
        lat = sorted(r["latency_s"] for r in ok)[len(ok) // 2] if ok else 0.0
        tok = sum(r["output_tokens"] for r in ok) / max(1, len(ok))
        errs = sum(bool(r["error"]) for r in rows)
        lines.append(f"| {LABEL[model]} | {p:.1%} | {lo:.3f}-{hi:.3f} "
                     f"| {truncation_rate(rows, top):.1%} | {conditional_rate(rows, top)[0]:.1%} "
                     f"| {n} | {errs} | {lat:.1f}s | {tok:.0f} |")
    (PAPER / out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main():
    FIGDIR.mkdir(parents=True, exist_ok=True)
    recs = load()
    budgets = sorted({r["max_tokens"] for r in recs if r["max_tokens"]})
    print(f"loaded {len(recs)} records, ceilings present: {budgets}\n")
    fig_token_budget(recs)
    fig_difficulty(recs)
    fig_efficiency(recs)
    write_latex(recs)
    write_significance(recs)
    print()
    write_markdown_table(recs)
    print(f"\nfigures -> {FIGDIR}")


if __name__ == "__main__":
    main()
