import os
import random
import time

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from app.agents.json_utils import extract_json_object

load_dotenv()

NEMOTRON_MODEL = "nvidia/nemotron-3-super-120b-a12b"

nim_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
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
    response = nim_client.chat.completions.create(
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
    return response.choices[0].message.content


def call_nim_json(model: str, system_prompt: str, user_prompt: str, retries: int = 1) -> dict:
    last_error: Exception | None = None
    for _ in range(retries + 1):
        raw = call_nim(model, system_prompt, user_prompt, temperature=0.2, max_tokens=2048)
        try:
            return extract_json_object(raw)
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"{model} did not return valid JSON after {retries + 1} attempts: {last_error}")


def call_nemotron(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 1024) -> str:
    return call_nim(NEMOTRON_MODEL, system_prompt, user_prompt, temperature, max_tokens)


def call_nemotron_json(system_prompt: str, user_prompt: str, retries: int = 2) -> dict:
    return call_nim_json(NEMOTRON_MODEL, system_prompt, user_prompt, retries)


if __name__ == "__main__":
    result = call_nemotron(
        system_prompt="You are a helpful assistant.",
        user_prompt="Which number is larger, 9.11 or 9.8?",
    )
    print(result)
