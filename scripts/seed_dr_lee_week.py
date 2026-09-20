"""Seeds one full week of Dr. Lee's calendar for the live rearrangement demo.

Run from the repo root:
    python scripts/seed_dr_lee_week.py

Clears and re-seeds appointments + preference_records (single-provider demo,
so the earlier multi-provider seed_demo_data.py scenario is replaced, not
merged with).

The scenario, by design:

1. You cancel Tuesday 10:00 AM live on the frontend.
2. Nemotron's top match is Maria, who is ALREADY booked Thursday 8:00 AM but
   whose stored preference is Tuesday mornings with Dr. Lee only - the
   dashboard shows this as a REARRANGEMENT (not a plain fill): accepting it
   moves her and frees her old Thursday 8:00 AM slot.
3. Thursday 8:00 AM opens -> Nemotron's top match is Noah, ALREADY booked
   the awkward Friday 4:45 PM slot (right before close) but whose stored
   preference is early Thursday mornings. Accepting moves him too, freeing
   Friday 4:45 PM.
4. Friday 4:45 PM opens -> the only remaining eligible candidate (Owen) is a
   weak match (flexible, no strong time preference) - the offer times out,
   the queue exhausts, and the incentive fallback kicks in automatically.
   Owen is also written as a customer who hasn't been in for months and
   mentions his son Max - stored preference text the phone agent can draw
   on for a personal, relationship-building call, not just a slot pitch.

Two owner clicks (rearrange, rearrange) + one real approved call. Nothing
about steps 2-4 is scripted UI behavior - it is the real ranking/matching/
incentive pipeline reacting to real stored data, exactly as it would for
any other cancellation.
"""

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from datetime import date, datetime, timedelta  # noqa: E402

from app.db.models.appointment import Appointment  # noqa: E402
from app.db.models.preference import PreferenceRecord  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402

PROVIDER = "Dr. Lee"
SERVICE = "Cleaning"
DURATION = 30
PRICE = 120.0


def next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def at(monday: date, day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(monday.year, monday.month, monday.day, hour, minute) + timedelta(days=day_offset)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        appt_deleted = db.query(Appointment).delete()
        pref_deleted = db.query(PreferenceRecord).delete()
        db.commit()

        monday = next_monday()
        far_expiry = (date.today() + timedelta(days=30)).isoformat()

        # (customer_id, day_offset Mon=0..Fri=4, hour, minute, status)
        # THE cancel target: Tuesday 10:00 AM - status "booked", cancel this
        # one live on the frontend to start the whole chain.
        SLOTS = [
            ("patient-alan", 0, 9, 0, "booked"),
            ("patient-beth", 0, 11, 0, "booked"),
            ("patient-carl", 0, 14, 0, "booked"),
            (None, 0, 16, 0, "available"),
            (None, 1, 9, 0, "available"),
            ("existing-patient-tue10", 1, 10, 0, "booked"),  # <- cancel this one live
            ("patient-dana", 1, 13, 0, "booked"),
            ("patient-eli", 1, 15, 0, "booked"),
            ("patient-fay", 2, 9, 0, "booked"),
            ("patient-gus", 2, 11, 30, "booked"),
            ("patient-hana", 2, 14, 0, "booked"),
            ("patient-maria", 3, 8, 0, "booked"),  # currently booked; wants Tue AM
            ("patient-ivan", 3, 10, 0, "booked"),
            ("patient-jill", 3, 13, 0, "booked"),
            ("patient-kim", 3, 15, 30, "booked"),
            ("patient-liam", 4, 9, 0, "booked"),
            ("patient-mona", 4, 11, 0, "booked"),
            ("patient-nora", 4, 13, 0, "booked"),
            ("patient-noah", 4, 16, 45, "booked"),  # currently booked; wants Thu early AM
        ]
        for customer_id, day_offset, hour, minute, status in SLOTS:
            db.add(Appointment(
                customer_id=customer_id,
                service=SERVICE,
                provider=PROVIDER,
                start_time=at(monday, day_offset, hour, minute),
                duration_minutes=DURATION,
                price=PRICE,
                status=status,
            ))
        db.commit()

        # patient_id, raw_text, hard_constraints, soft_preferences, requested_time
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
                "patient-owen",
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

        print(
            f"cleared {appt_deleted} appointments, {pref_deleted} preference records; "
            f"seeded {len(SLOTS)} appointments, {len(PREFERENCE_RECORDS)} preference records"
        )
        print(f"Week of {monday.isoformat()} (Mon-Fri), Dr. Lee only.")
        print("Cancel Tuesday 10:00 AM live to start the chain.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
