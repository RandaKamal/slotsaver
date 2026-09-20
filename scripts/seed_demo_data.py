"""Owner: Randa. Seeds the SQLite database with demo appointment slots and
patient preference records.

Run from anywhere, e.g. from the repo root:
    python scripts/seed_demo_data.py

Clears and re-seeds the appointments and preference_records tables every
run, so it's safe to use before each demo/test pass.
"""

import sys
from pathlib import Path

# scripts/seed_demo_data.py -> repo root -> apps/api (where the `app` package lives)
_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from datetime import date, datetime, timedelta  # noqa: E402

from app.db.models.appointment import Appointment  # noqa: E402
from app.db.models.preference import PreferenceRecord  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402


def upcoming(weekday: int, hour: int, minute: int = 0) -> datetime:
    """Next occurrence of `weekday` (Mon=0..Sun=6) at hour:minute, always in the future."""
    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += timedelta(days=(weekday - now.weekday()) % 7)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


# (customer_id, service, provider, weekday, hour, minute, duration_min, price, status)
SLOTS = [
    (None, "Follow-up Consultation", "Dr. Lee", 0, 10, 0, 45, 120.0, "available"),
    (None, "Annual Physical", "Dr. Lee", 2, 9, 0, 60, 180.0, "available"),
    ("existing-patient-42", "Follow-up Consultation", "Dr. Lee", 4, 13, 0, 45, 120.0, "booked"),
    (None, "Follow-up Consultation", "Dr. Lee", 4, 14, 0, 45, 120.0, "available"),
    (None, "Brief Consultation", "Dr. Lee", 4, 16, 0, 30, 90.0, "available"),
    (None, "Brief Consultation", "Dr. Patel", 1, 11, 0, 30, 90.0, "available"),
    (None, "Follow-up Consultation", "Dr. Patel", 3, 15, 0, 45, 120.0, "available"),
    (None, "Annual Physical", "Dr. Patel", 4, 10, 0, 60, 180.0, "available"),
]

_FAR_EXPIRY = (date.today() + timedelta(days=30)).isoformat()

# Mix of eligible / hard-excluded / opted-out patients, so cancelling the
# Friday 1 PM Dr. Lee slot (existing-patient-42, above) has real deterministic
# eligibility work to do: recovery_matcher.find_candidates reads exactly
# these rows, nothing mocked.
PREFERENCE_RECORDS = [
    # patient_id, raw_text, status, notify_if_opens, hard_constraints,
    # soft_preferences, requested_time, expiry, earlier_if_possible
    dict(
        patient_id="demo-patient-1",
        raw_text="Call me if anything with Dr. Lee opens up, afternoons are best, just not Tuesdays.",
        status="extracted",
        notify_if_opens=True,
        hard_constraints={"excluded_days": ["Tuesday"]},
        soft_preferences={"preferred_provider": "Dr. Lee", "provider_flexible": True},
        requested_time="afternoon",
        expiry=_FAR_EXPIRY,
        earlier_if_possible=True,
    ),
    dict(
        patient_id="demo-patient-2",
        raw_text="I'll see anyone but Dr. Patel, and I'd love an earlier slot this month.",
        status="extracted",
        notify_if_opens=True,
        hard_constraints={"excluded_providers": ["Dr. Patel"]},
        soft_preferences={"preferred_provider": None, "provider_flexible": True},
        requested_time="morning",
        expiry=_FAR_EXPIRY,
        earlier_if_possible=True,
    ),
    dict(
        patient_id="demo-patient-3",
        raw_text="Only Dr. Lee for me, no one else. Afternoons if you can.",
        status="extracted",
        notify_if_opens=True,
        hard_constraints={},
        soft_preferences={"preferred_provider": "Dr. Lee", "provider_flexible": False},
        requested_time="afternoon",
        expiry=_FAR_EXPIRY,
        earlier_if_possible=False,
    ),
    # Excluded by a hard constraint: Fridays are out entirely.
    dict(
        patient_id="demo-patient-4",
        raw_text="Anything but a Friday works for me.",
        status="extracted",
        notify_if_opens=True,
        hard_constraints={"excluded_days": ["Friday"]},
        soft_preferences={"preferred_provider": None, "provider_flexible": True},
        requested_time=None,
        expiry=_FAR_EXPIRY,
        earlier_if_possible=False,
    ),
    # Excluded by soft preference: insists on a provider other than Dr. Lee.
    dict(
        patient_id="demo-patient-5",
        raw_text="I only want to see Dr. Patel, nobody else.",
        status="extracted",
        notify_if_opens=True,
        hard_constraints={},
        soft_preferences={"preferred_provider": "Dr. Patel", "provider_flexible": False},
        requested_time=None,
        expiry=_FAR_EXPIRY,
        earlier_if_possible=False,
    ),
    # Never considered at all: didn't opt in to being notified.
    dict(
        patient_id="demo-patient-6",
        raw_text="Just booking my regular visit, no need to call me about openings.",
        status="extracted",
        notify_if_opens=False,
        hard_constraints={},
        soft_preferences={},
        requested_time=None,
        expiry=None,
        earlier_if_possible=False,
    ),
    # Never considered at all: extraction hasn't finished (still "pending").
    dict(
        patient_id="demo-patient-7",
        raw_text="Let me know if something opens sooner, ideally with Dr. Lee.",
        status="pending",
        notify_if_opens=True,
        hard_constraints=None,
        soft_preferences=None,
        requested_time=None,
        expiry=None,
        earlier_if_possible=False,
    ),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        deleted_appts = db.query(Appointment).delete()
        for (
            customer_id,
            service,
            provider,
            weekday,
            hour,
            minute,
            duration,
            price,
            status,
        ) in SLOTS:
            db.add(
                Appointment(
                    customer_id=customer_id,
                    service=service,
                    provider=provider,
                    start_time=upcoming(weekday, hour, minute),
                    duration_minutes=duration,
                    price=price,
                    status=status,
                )
            )

        deleted_prefs = db.query(PreferenceRecord).delete()
        for row in PREFERENCE_RECORDS:
            db.add(
                PreferenceRecord(
                    patient_id=row["patient_id"],
                    raw_text=row["raw_text"],
                    status=row["status"],
                    notify_if_opens=row["notify_if_opens"],
                    hard_constraints=row["hard_constraints"],
                    soft_preferences=row["soft_preferences"],
                    requested_time=row["requested_time"],
                    expiry=row["expiry"],
                    raw_extraction={"earlier_if_possible": row["earlier_if_possible"]},
                )
            )

        db.commit()
        print(
            f"cleared {deleted_appts} appointments, seeded {len(SLOTS)}; "
            f"cleared {deleted_prefs} preference records, seeded {len(PREFERENCE_RECORDS)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
