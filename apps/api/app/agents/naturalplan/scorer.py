"""Scoring for NATURAL PLAN calendar scheduling.

Ported verbatim in behaviour from Google DeepMind's official evaluator so our
numbers are directly comparable to the published ones:

    https://github.com/google-deepmind/natural-plan
    evaluate_calendar_scheduling.py, Apache License 2.0, Copyright 2024 Google LLC

Paper: Zheng et al., "NATURAL PLAN: Benchmarking LLMs on Natural Language
Planning", arXiv:2406.04520.

Scoring is exact match on (day, start, end) after a regex parse - no LLM judge
and no human labelling, which is the entire reason for using this benchmark
rather than a hand-labelled one.
"""

import re

_TIME_RE = re.compile(r"[A-Za-z]+, [0-9]+:[0-9]+ - [0-9]+:[0-9]+")


def hour_to_num(hr_str: str) -> float:
    return float(hr_str.split(":")[0]) + (0.5 if hr_str.split(":")[1] == "30" else 0.0)


def parse_response(response: str) -> tuple[str, float, float]:
    """Returns (day, start_hour, end_hour); ('', -1, -1) when nothing parses."""
    if not response:
        return "", -1.0, -1.0
    matches = _TIME_RE.findall(response)
    if not matches:
        return "", -1.0, -1.0
    time_str = matches[0]  # official evaluator takes the first match
    day = time_str.split(",")[0].strip()
    hour_str = time_str.split(",")[1].strip()
    start_hour, end_hour = hour_str.split("-")[0].strip(), hour_str.split("-")[1].strip()
    return day, hour_to_num(start_hour), hour_to_num(end_hour)


def is_solved(response: str, golden: str) -> bool:
    return parse_response(response) == parse_response(golden)


def solve_rate(responses: list[str], goldens: list[str]) -> float:
    if not responses:
        return 0.0
    return sum(is_solved(r, g) for r, g in zip(responses, goldens)) / len(responses)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval.

    Reported instead of a bare accuracy because at a few hundred samples the
    difference between two models is often inside the noise, and a paper that
    prints point estimates alone cannot show that.
    """
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def mcnemar(a_correct: list[bool], b_correct: list[bool]) -> dict:
    """Exact McNemar test on paired per-item outcomes.

    Two models are run on the SAME items, so their scores are paired and a
    two-sample proportion test is the wrong instrument: it throws away the
    pairing and overstates the uncertainty. McNemar conditions on the
    discordant pairs only, which is the information that actually distinguishes
    the two systems.

    Returns the discordant counts and an exact two-sided binomial p-value, so
    no normal approximation is involved and small counts stay valid.
    """
    if len(a_correct) != len(b_correct):
        raise ValueError("paired test needs equal-length outcome lists")
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)  # a wins
    c = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)  # b wins
    n = b + c
    if n == 0:
        return {"a_only": 0, "b_only": 0, "n_discordant": 0, "p_value": 1.0}

    # Exact two-sided binomial test against p = 0.5, computed directly so the
    # module keeps no scipy dependency.
    from math import comb

    total = 2 ** n
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1))
    p = min(1.0, 2.0 * tail / total)
    return {"a_only": b, "b_only": c, "n_discordant": n, "p_value": p}
