import logging
import os
import random
import time

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from app.agents.json_utils import extract_json_object

load_dotenv()

logger = logging.getLogger(__name__)

NEMOTRON_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# NVIDIA rate-limits per MODEL, not per account: the 120B saturating does not
# mean the key is out of budget - a smaller Nemotron on its own bucket still
# answers. Tried in order when the one before it is rate-limited or has been
# retired (nemotron-nano-9b-v2 was EOL'd out from under this project
# mid-build), so a throttle degrades to a smaller model of the same family
# instead of to no ranking at all.
#
# Deliberately NOT applied to call_nim/call_nim_json: the benchmark harness
# and baselines.py compare NAMED models, and quietly answering as a different
# one would corrupt exactly what they measure.
NEMOTRON_FALLBACK_MODELS = ("nvidia/nemotron-3.5-lightning-30b-a3b",)

nim_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    # A missing key should fail the NIM call that needs it (caught in
    # preference_service's background task) at request time, not crash the
    # whole app at import time for every route, including ones that never
    # touch Nemotron. The OpenAI client itself rejects a falsy api_key even
    # at construction, so an empty env var needs a non-empty placeholder -
    # the real 401 still happens the first time a call is actually made.
    api_key=os.environ.get("NVIDIA_API_KEY") or "missing-nvidia-api-key",
    timeout=60.0,
    max_retries=1,
)


# NVIDIA's shared endpoint returns 503 "Service temporarily overloaded" under
# concurrency. These are transient and worth retrying with backoff; a bad
# request or auth failure is not, and is re-raised immediately.
_TRANSIENT = (InternalServerError, RateLimitError, APITimeoutError, APIConnectionError)


def _with_backoff(fn, attempts: int = 4, base: float = 1.5):
    for attempt in range(attempts):
        try:
            return fn()
        except _TRANSIENT:
            if attempt == attempts - 1:
                raise
            # Jitter so parallel callers don't retry in lockstep and re-collide.
            time.sleep(base ** attempt + random.uniform(0, 0.75))
    raise RuntimeError("unreachable")


def call_nim(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.5,
    max_tokens: int = 1024,
    detailed_thinking: bool = False,
) -> str:
    """Generic call to any model hosted on NVIDIA's NIM endpoint (Nemotron, Mistral-Nemotron, etc).

    detailed_thinking=False skips a reasoning model's chain-of-thought trace, which otherwise
    eats the max_tokens budget before it emits the actual answer (NVIDIA Nemotron reasoning
    toggle: appended to the system prompt per NVIDIA's docs). Models that don't support the
    toggle just ignore the extra text.
    """
    thinking_suffix = "\n\ndetailed thinking on" if detailed_thinking else "\n\ndetailed thinking off"
    response = _with_backoff(
        lambda: nim_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt + thinking_suffix},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            top_p=1,
            max_tokens=max_tokens,
            stream=False,
        )
    )
    content = response.choices[0].message.content
    if content is None:
        # A filtered or reasoning-only completion yields None, and handing that
        # to json.loads raises TypeError - which call_nim_json's retry did not
        # catch, so every remaining attempt was skipped. ValueError keeps it on
        # the retryable path.
        raise ValueError(f"{model} returned an empty completion (content=None)")
    return content


def call_nim_json(model: str, system_prompt: str, user_prompt: str, retries: int = 1) -> dict:
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            # The model call belongs INSIDE the try: it was outside, so a
            # transport error or an empty completion escaped the loop and
            # burned every remaining retry. TypeError is caught alongside
            # ValueError because json.loads raises it on a non-string.
            raw = call_nim(model, system_prompt, user_prompt, temperature=0.2, max_tokens=2048)
            return extract_json_object(raw)
        except (ValueError, TypeError) as exc:
            last_error = exc
    raise ValueError(f"{model} did not return valid JSON after {retries + 1} attempts: {last_error}")


# A model being throttled or retired is about that model's availability, not
# about the request being wrong - those are the two cases worth re-asking a
# different Nemotron. A 400/401 would fail identically on every model, so it
# is raised immediately rather than retried down the chain.
_MODEL_UNAVAILABLE = (RateLimitError, NotFoundError)


def _nemotron_chain() -> tuple[str, ...]:
    return (NEMOTRON_MODEL, *NEMOTRON_FALLBACK_MODELS)


def call_nemotron(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 1024) -> str:
    last_error: Exception | None = None
    for model in _nemotron_chain():
        try:
            return call_nim(model, system_prompt, user_prompt, temperature, max_tokens)
        except _MODEL_UNAVAILABLE as exc:
            logger.warning("nemotron model %s unavailable (%s) - trying next in chain", model, type(exc).__name__)
            last_error = exc
    raise last_error  # type: ignore[misc]


def call_nemotron_json(system_prompt: str, user_prompt: str, retries: int = 2) -> dict:
    last_error: Exception | None = None
    for model in _nemotron_chain():
        try:
            return call_nim_json(model, system_prompt, user_prompt, retries)
        except _MODEL_UNAVAILABLE as exc:
            logger.warning("nemotron model %s unavailable (%s) - trying next in chain", model, type(exc).__name__)
            last_error = exc
    raise last_error  # type: ignore[misc]


if __name__ == "__main__":
    result = call_nemotron(
        system_prompt="You are a helpful assistant.",
        user_prompt="Which number is larger, 9.11 or 9.8?",
    )
    print(result)
