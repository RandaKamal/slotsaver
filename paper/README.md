# Reproducibility package

Everything needed to reproduce the figures, tables and numbers in
`main.tex`, including the raw per call records.

## What is here

| Path | What it is |
|---|---|
| `main.tex` | Paper source. Compiles on arXiv as is. |
| `references.bib` | 8 citations. |
| `numbers.tex` | Every numeric claim in the prose, generated from the data. Not hand written. |
| `table_main.tex`, `table_sig.tex` | Results and significance tables, generated. |
| `figures/*.png` | Generated at 200 dpi. |
| `../results/naturalplan_*.json` | Raw per call records, including the first 400 characters of every generation. |

## Reproducing from scratch

```bash
# 1. Fetch the benchmark (Apache-2.0 / CC-BY, downloaded on first run)
#    github.com/google-deepmind/natural-plan

# 2. Run the experiment. Ceilings are swept in one invocation.
python scripts/run_naturalplan.py \
    --per-bucket 10 --shots 5 \
    --max-tokens 512 1024 2048 4096 \
    --models nemotron claude gemini \
    --workers 5

# 3. Rebuild every figure, table and numeric macro from the results
python scripts/make_figures.py

# 4. Static check of the paper source before submitting
python scripts/check_paper.py
```

Requires `NVIDIA_API_KEY`, `ANTHROPIC_API_KEY` and `GEMINI_API_KEY`.

## Design decisions a reviewer will want to check

**Scoring is not ours.** `apps/api/app/agents/naturalplan/scorer.py` reproduces
the behaviour of the official evaluator from the benchmark repository. We
validated it before running anything: it scores the reference predictions
shipped with the dataset at 48.9%, against 48% reported in the original paper.

**No per model prompt tuning.** Every model receives the byte identical prompt
string taken from the dataset. There is no system prompt beyond the vendor
recommended reasoning toggle for Nemotron, and no reformatting.

**The ceiling is shared.** Within any single comparison, every model gets the
same `max_tokens`. The sweep varies it for all models together, never for one.

**Latency excludes our own backoff.** Retry sleeps happen outside the timed
region, so a model that our free tier rate limited does not appear slow. This
mattered: an earlier version timed the retry loop and made Gemini look six times
slower than it is.

**Sampling is stratified and seeded.** The raw dataset is half two participant
items, so a uniform sample would mostly measure the easiest bucket. We draw an
equal number from each participant count. The seed is recorded in every result
file.

**Pairing is respected.** All models see the same items, so model comparisons
use exact McNemar tests on paired outcomes rather than a two sample proportion
test.

## Known limitations

These are stated in the paper and repeated here so they are not missed.

1. **Contamination is not controlled.** The benchmark has been public since
   2024. Exposure is symmetric across the three models, and the headline result
   is a within model effect, but we make no decontamination claim.
2. **Claude runs at the API default temperature.** The Anthropic Python SDK
   version used removed `temperature` from `messages.create`; the replacement
   `output_config` exposes only `effort` and `format`. The other two models run
   at temperature 0.
3. **Hosted endpoints, not weights.** Vendor side changes are invisible to us.
   Results are tied to the run date in the paper.
4. **Truncation is inferred from token counts**, since not every SDK surfaces a
   finish reason consistently. A generation whose output token count equals the
   ceiling is counted as truncated.
