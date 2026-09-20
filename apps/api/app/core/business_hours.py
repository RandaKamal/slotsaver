"""Turns a business profile's open/close hours into the three time-of-day
buckets ("morning"/"afternoon"/"evening") the voice tools and recovery
matcher filter on.

Previously these were two independently hardcoded copies of the same
8am-9pm dental-clinic schedule (appointment_service.py and
recovery_matcher.py). Splitting the profile's actual hours into thirds keeps
the same bucket *shape* for any business - a 9-to-5 tutoring center and a
10am-8pm barbershop each get sensible morning/afternoon/evening windows
without a business-type-specific rule.
"""

TimeOfDayRanges = dict[str, tuple[int, int]]

_DEFAULT_OPEN_HOUR = 8
_DEFAULT_CLOSE_HOUR = 21


def _hour(value: str, default: int) -> int:
    try:
        return int(value.split(":")[0])
    except (ValueError, IndexError, AttributeError):
        return default


def compute_time_of_day_ranges(open_time: str, close_time: str) -> TimeOfDayRanges:
    open_hour = _hour(open_time, _DEFAULT_OPEN_HOUR)
    close_hour = _hour(close_time, _DEFAULT_CLOSE_HOUR)
    if close_hour <= open_hour:
        close_hour = open_hour + 1

    third = max(1, (close_hour - open_hour) // 3)
    morning_end = open_hour + third
    afternoon_end = open_hour + 2 * third

    return {
        "morning": (open_hour, morning_end),
        "afternoon": (morning_end, afternoon_end),
        # Open-ended so a slot after close (e.g. running late) still buckets
        # as "evening" instead of matching nothing, matching prior behavior.
        "evening": (afternoon_end, 24),
    }


def time_of_day_for_hour(hour: int, ranges: TimeOfDayRanges) -> str:
    for name, (lo, hi) in ranges.items():
        if lo <= hour < hi:
            return name
    return "evening"
