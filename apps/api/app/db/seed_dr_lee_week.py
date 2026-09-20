"""Same scenario as scripts/seed_dr_lee_week.py, importable so it can be
triggered over HTTP (see api/routes/dev_seed.py) against whichever database
DATABASE_URL already points the running process at - avoids needing the
production connection string on a local machine just to seed a demo.

Always clears and re-seeds (single-provider demo, replaces any earlier
multi-provider scenario) - see the CLI script for the full narrative this
data is built for.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.db.models.preference import PreferenceRecord

PROVIDER = "Dr. Lee"
SERVICE = "Cleaning"
DURATION = 30
PRICE = 120.0


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _at(monday: date, day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(monday.year, monday.month, monday.day, hour, minute) + timedelta(days=day_offset)


def seed_dr_lee_week(db: Session) -> dict:
    appt_deleted = db.query(Appointment).delete()
    pref_deleted = db.query(PreferenceRecord).delete()
    db.commit()

    monday = _next_monday()
    far_expiry = (date.today() + timedelta(days=30)).isoformat()

    SLOTS = [
        ("patient-alan", 0, 9, 0, "booked"),
        ("patient-beth", 0, 11, 0, "booked"),
        ("patient-carl", 0, 14, 0, "booked"),
        (None, 0, 16, 0, "available"),
        (None, 1, 9, 0, "available"),
        ("existing-patient-tue10", 1, 10, 0, "booked"),
        ("patient-dana", 1, 13, 0, "booked"),
        ("patient-eli", 1, 15, 0, "booked"),
        ("patient-fay", 2, 9, 0, "booked"),
        ("patient-gus", 2, 11, 30, "booked"),
        ("patient-hana", 2, 14, 0, "booked"),
        ("patient-maria", 3, 8, 0, "booked"),
        ("patient-ivan", 3, 10, 0, "booked"),
        ("patient-jill", 3, 13, 0, "booked"),
        ("patient-kim", 3, 15, 30, "booked"),
        ("patient-liam", 4, 9, 0, "booked"),
        ("patient-mona", 4, 11, 0, "booked"),
        ("patient-nora", 4, 13, 0, "booked"),
        ("patient-noah", 4, 16, 45, "booked"),
    ]
    for customer_id, day_offset, hour, minute, status in SLOTS:
        db.add(Appointment(
            customer_id=customer_id,
            service=SERVICE,
            provider=PROVIDER,
            start_time=_at(monday, day_offset, hour, minute),
            duration_minutes=DURATION,
            price=PRICE,
            status=status,
        ))
    db.commit()

    PREFERENCE_RECORDS = [
        (
            "patient-maria",
            "I love coming to Dr. Lee, but these early Thursday appointments are "
            "brutal - I have to get my daughter Sophie to school first. If a "
            "Tuesday morning ever opens up with Dr. Lee I would switch in a "
            "heartbeat, mornings only please.",
            {"excluded_providers": []},
            {"preferred_time_ranges": ["morning"], "preferred_provider": "Dr. Lee", "provider_flexible": False},
            "morning",
        ),
        (
            "patient-noah",
            "Early mornings actually work best for me before my shift starts. "
            "That late Friday slot right before you close is rough, I'm always "
            "rushing straight from work. Dr. Lee only for me, and mornings if "
            "you can swing it.",
            {"excluded_providers": []},
            {"preferred_time_ranges": ["morning"], "preferred_provider": "Dr. Lee", "provider_flexible": False},
            "morning",
        ),
        (
            "Kevin",
            "Honestly it's been ages since I've been in - I think my last "
            "cleaning was something like 8 months ago, sorry! My son Max just "
            "started high school so things have been hectic. I'm pretty "
            "flexible on timing, just let me know if anything opens up.",
            {"excluded_providers": []},
            {"preferred_time_ranges": [], "preferred_provider": None, "provider_flexible": True},
            None,
        ),
    ]
    for patient_id, raw_text, hard, soft, requested_time in PREFERENCE_RECORDS:
        db.add(PreferenceRecord(
            patient_id=patient_id,
            raw_text=raw_text,
            status="extracted",
            notify_if_opens=True,
            hard_constraints=hard,
            soft_preferences=soft,
            requested_time=requested_time,
            expiry=far_expiry,
            phone_number=None,
        ))
    db.commit()

    return {
        "cleared_appointments": appt_deleted,
        "cleared_preferences": pref_deleted,
        "seeded_appointments": len(SLOTS),
        "seeded_preferences": len(PREFERENCE_RECORDS),
        "week_of": monday.isoformat(),
    }
