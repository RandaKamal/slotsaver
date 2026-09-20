"""Model runners for the NATURAL PLAN calendar-scheduling experiment.

Every model gets the byte-identical prompt straight from the dataset - no
per-model prompt tuning - so the comparison measures the model, not our
prompt-writing. Token counts and wall-clock latency are captured per call
because accuracy alone cannot support a cost- or efficiency-normalised claim.
"""

import os
import random
import threading
import time
from dataclasses import dataclass, field

from app.agents.nemotron.client import _TRANSIENT, _with_backoff, nim_client

NEMOTRON_MODEL = "nvidia/nemotron-3-super-120b-a12b"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
# gemini-3.6-flash caps the free tier at 20 requests, too few to run this
# experiment. gemini-3.5-flash is the nearest available flash-tier model with
# workable quota, so it is the tier-matched comparator against Claude Haiku 4.5
# and Nemotron Super. Measured: 11/12 succeed at 2s spacing.
GEMINI_MODEL = "gemini-3.5-flash"

# Nemotron is a sparse MoE: 120B total parameters, ~12B active per token.
# Claude and Gemini parameter counts are NOT published - do not invent them.
NEMOTRON_TOTAL_PARAMS_B = 120
NEMOTRON_ACTIVE_PARAMS_B = 12


@dataclass
class ModelResult:
    text: str = ""
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    # Authoritative truncation signal from the vendor. Counting emitted tokens
    # and comparing against the ceiling is NOT reliable: a model that reasons in
    # hidden "thinking" tokens spends the budget without those tokens appearing
    # in the visible output count, so the naive check reports no truncation on
    # exactly the models where truncation matters most.
    finish_reason: str | None = None
    thinking_tokens: int = 0
    error: str | None = None
    meta: dict = field(default_factory=dict)


def _timed(fn) -> tuple[object, float]:
    """Times one request.

    Retry sleeps are deliberately OUTSIDE this: a model that got rate-limited
    by our own free-tier quota would otherwise look slow, which is an artefact
    of our billing plan rather than a property of the model.
    """
    start = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - start


def _retrying(call, is_retryable, attempts: int = 8, base: float = 2.0):
    """Returns (result, latency_of_successful_attempt)."""
    for attempt in range(attempts):
        try:
            return _timed(call)
        except Exception as exc:  # noqa: BLE001
            if not is_retryable(exc) or attempt == attempts - 1:
                raise
            time.sleep(min(base ** attempt, 32) + random.uniform(0, 1.0))
    raise RuntimeError("unreachable")


def run_nemotron(prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> ModelResult:
    try:
        response, elapsed = _retrying(
            lambda: nim_client.chat.completions.create(
                    model=NEMOTRON_MODEL,
                # The reasoning toggle goes in the system turn per NVIDIA's
                # docs; the benchmark prompt itself is left untouched.
                messages=[
                    {"role": "system", "content": "detailed thinking off"},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            ),
            is_retryable=lambda e: isinstance(e, _TRANSIENT),
        )
        usage = response.usage
        return ModelResult(
            text=response.choices[0].message.content or "",
            latency_s=elapsed,
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            finish_reason=str(getattr(response.choices[0], "finish_reason", "") or ""),
        )
    except Exception as exc:  # noqa: BLE001 - recorded, never fatal to a run
        return ModelResult(error=f"{type(exc).__name__}: {exc}")


def run_claude(prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> ModelResult:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ModelResult(error="ANTHROPIC_API_KEY not set")
    try:
        import anthropic

        client = anthropic.Anthropic(max_retries=4)
        # anthropic 1.7.0 removed `temperature` from messages.create (the
        # replacement output_config carries only `effort` and `format`), so
        # Claude runs at the API default while the other two run at 0. This is
        # an SDK constraint, not a choice - it must be stated as a limitation
        # rather than papered over.
        response, elapsed = _timed(
            lambda: client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return ModelResult(
            text=text,
            latency_s=elapsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=str(getattr(response, "stop_reason", "") or ""),
            meta={"temperature": "api_default (not settable in anthropic 1.7.0)"},
        )
    except Exception as exc:  # noqa: BLE001
        return ModelResult(error=f"{type(exc).__name__}: {exc}")


# Gemini's free tier rate-limits hard (429 RESOURCE_EXHAUSTED) well below the
# concurrency this harness uses. A semaphore keeps our own request rate sane and
# the retry loop absorbs the rest, so quota errors do not get recorded as
# planning failures - that would silently understate the model.
_GEMINI_GATE = threading.Lock()
_GEMINI_MIN_INTERVAL = 2.0  # seconds -> 30 rpm, measured safe for this model
_gemini_last_call = [0.0]


def _gemini_pace() -> None:
    """Blocks until enough time has passed since the previous Gemini request."""
    with _GEMINI_GATE:
        wait = _GEMINI_MIN_INTERVAL - (time.monotonic() - _gemini_last_call[0])
        if wait > 0:
            time.sleep(wait)
        _gemini_last_call[0] = time.monotonic()


def _gemini_retryable(exc: Exception) -> bool:
    msg = str(exc)
    if "PerDay" in msg or "RequestsPerDay" in msg or "per day" in msg.lower():
        return False  # the quota resets tomorrow, not in 32 seconds
    return any(
        s in msg
        for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "high demand")
    )


def run_gemini(prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> ModelResult:
    if not os.environ.get("GEMINI_API_KEY"):
        return ModelResult(error="GEMINI_API_KEY not set")
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        def _one():
            _gemini_pace()
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"temperature": temperature, "max_output_tokens": max_tokens},
            )

        response, elapsed = _retrying(
            _one,
            # 503 UNAVAILABLE ("high demand") is transient too, and scoring it
            # as a planning failure would understate the model. A PER DAY quota
            # exhaustion is emphatically NOT transient: retrying it burns hours
            # of wall clock to arrive at the same refusal, so it fails fast.
            is_retryable=_gemini_retryable,
        )
        um = getattr(response, "usage_metadata", None)
        cands = getattr(response, "candidates", None) or []
        finish = str(getattr(cands[0], "finish_reason", "") or "") if cands else ""
        # thoughts_token_count is billed against max_output_tokens but is absent
        # from candidates_token_count, which is why the token proxy under-reports
        # truncation for this model.
        thinking = getattr(um, "thoughts_token_count", 0) or 0
        return ModelResult(
            text=response.text or "",
            latency_s=elapsed,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
            finish_reason=finish,
            thinking_tokens=thinking,
        )
    except Exception as exc:  # noqa: BLE001
        return ModelResult(error=f"{type(exc).__name__}: {exc}")


RUNNERS = {
    "nemotron": run_nemotron,
    "claude": run_claude,
    "gemini": run_gemini,
}

MODEL_IDS = {
    "nemotron": NEMOTRON_MODEL,
    "claude": CLAUDE_MODEL,
    "gemini": GEMINI_MODEL,
}
