# RecoveryBench

Owner: Kevin. Benchmark methodology and results (real, executed cases only).

---

## Extraction A/B: does the self-critique pass help? (2026-09-19)

`app/agents/extraction_bench.py`, cases in `apps/api/tests/fixtures/extraction_cases.json`.
Run: `python scripts/run_extraction_bench.py`

Measures one thing: **single-pass vs two-pass extraction on identical cases with
identical labels**. Unlike the cross-model benchmark above, this comparison is
internally fair even with hand-written labels, because label bias lands on both
arms equally. It says nothing about Nemotron vs Gemini vs Claude.

Graded per assertion (23 across 10 cases), not per case.

| run | single-pass | two-pass | delta | cases critique touched |
|-----|-------------|----------|-------|------------------------|
| 1   | 0.957       | 1.000    | +0.043 | 3 / 10 |
| 2   | 0.957       | 0.957    |  0.000 | 4 / 10 |

**Conclusion: no reliable improvement demonstrated.** One assertion out of 23 is
worth 0.043, so run 1's entire "gain" was a single assertion, and it did not
reproduce. Two runs cannot distinguish a real effect from noise. Do not claim
the self-critique improves accuracy.

What the pass is good for, and what it is not:

- It **did** fix a real error once (`valid_until` off by one day on
  `surgery_deadline`), and post-redesign it has produced no regressions.
- It costs the caller nothing, because it runs in the background task, never on
  the request path.
- It is **not** evidence of self-improvement, and is not currently defensible as
  a headline metric.

### Two findings worth keeping

**The first critique design corrupted data.** It rewrote the whole extraction
object, and on one case mangled a list it had not been asked about — dropped
`Sunday`, duplicated `Saturday`. It now returns only targeted field corrections,
which are merged path-by-path into the draft; unknown paths are rejected and any
malformed response falls back to the draft. A bad critique can no longer produce
a result worse than no critique.

**Two of the three original "model failures" were bad labels.** `surgery_deadline`
expected `2026-10-03` for "before my surgery on October 3rd" — the last useful day
is the 2nd. `relative_expiry` expected `2026-10-02` for "end of next week" when
today is Sat 2026-09-19 — next week ends 09-27. The model was right and the
fixture was wrong, in both cases written by the same author as the prompt. Both
labels are corrected and annotated in the fixture.

This is the circularity problem in this document's opening caveat, caught
concretely. It is the strongest argument available for getting a teammate to
blind-label a fresh batch: self-authored labels were measurably wrong here, and
would have been reported as model errors.

### The defensible claim right now

Not "Nemotron beats X on accuracy". Instead:

> Moving extraction off the request path cut what the voice agent waits from a
> measured **12.75s median to 0.027s** — a ~470x reduction — which removes the
> mid-call silence that caused a real ElevenLabs tool call to be abandoned in
> production. Accuracy on the extraction suite is unchanged.

That is measured, reproducible, and does not depend on contested labels.
