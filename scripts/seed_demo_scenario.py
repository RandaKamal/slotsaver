"""Seeds the cancellation-recovery demo: the Maria scenario.

The story this sets up, taken from a real SlotSaver voice call:

  Maria calls wanting Dr. Patel on Monday at 6pm. No such slot is open. A
  normal booking agent ends the call there - patient lost, slot never filled.
  SlotSaver instead stores her INTENT: Monday only, 18:00, Dr. Patel, contact
  me if it opens, and worthless to me after Monday because I fly to Germany.

  Then another patient cancels that exact slot. Maria is the only person in
  the system it fits, and her window closes tomorrow.

Run after seed_demo_data.py:
    python scripts/seed_demo_scenario.py

Runs the real Nemotron extractor so the stored intent on screen is genuinely
model-derived, with a precomputed fallback if the API is unreachable mid-demo.
"""

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

import datetime  # noqa: E402

from app.db.models.appointment import Appointment  # noqa: E402
from app.db.models.preference import PreferenceRecord  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402

MARIA = "maria-k"
# A second patient who also wants to be told about openings, but fits this slot
# worse: no provider loyalty, prefers mornings, and is under no time pressure.
# Having them in the pool is what makes the ranking a decision rather than a
# formality.
TOM = "tom-r"
TOM_SAID = (
    "Mornings are much better for me, any doctor is fine. Give me a ring if anything "
    "opens up in the next few weeks."
)
TOM_EXTRACTION = {
    "hard_constraints": {"excluded_days": [], "excluded_providers": []},
    "soft_preferences": {
        "preferred_time_ranges": ["morning"],
        "preferred_provider": None,
        "provider_flexible": True,
    },
    "earlier_if_possible": False,
    "notify_if_opens": True,
    "requested_time": None,
    "valid_until": None,
    "contact_preference": "phone",
    "confidence": 0.9,
}
SAID = (
    "I'm only available at 6:00 p.m. on Monday, and after that date I'll be flying back "
    "to Germany. Let me know once that slot opens."
)
CONTEXT = (
    "Patient asked to see Dr. Patel specifically and said she won't switch doctors. "
    "Agent checked and told her no Monday evening slots with Dr. Patel are open."
)


def next_monday_6pm() -> datetime.datetime:
    now = datetime.datetime.now()
    d = now.replace(hour=18, minute=0, second=0, microsecond=0)
    d += datetime.timedelta(days=(0 - now.weekday()) % 7)
    return d + datetime.timedelta(days=7) if d <= now else d


def _fallback(monday: datetime.datetime) -> dict:
    """Known-good extraction, used only if the NIM endpoint is down."""
    return {
        "hard_constraints": {
            "excluded_days": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "excluded_providers": [],
        },
        "soft_preferences": {
            "preferred_time_ranges": ["evening"],
            "preferred_provider": "Dr. Patel",
            "provider_flexible": False,
        },
        "earlier_if_possible": False,
        "notify_if_opens": True,
        "requested_time": "18:00",
        "valid_until": monday.date().isoformat(),
        "contact_preference": None,
        "confidence": 0.95,
    }


def main() -> None:
    Base.metadata.create_all(bind=engine)
    monday = next_monday_6pm()

    try:
        from app.agents.nemotron.preference_extractor import (
            extract_preferences,
            refine_preferences,
        )

        print("running real Nemotron extraction (~15s)...")
        draft = extract_preferences(SAID, MARIA, context=CONTEXT, today=datetime.date.today())
        extracted = refine_preferences(SAID, draft, context=CONTEXT, today=datetime.date.today())
        source = "nemotron"
    except Exception as exc:  # noqa: BLE001 - demo must still run offline
        print(f"  extraction unavailable ({type(exc).__name__}), using precomputed fallback")
        extracted, source = _fallback(monday), "fallback"

    db = SessionLocal()
    try:
        # Deterministic demo: drop anything left over from manual testing so the
        # candidate pool is exactly the two patients below.
        db.query(PreferenceRecord).delete()
        db.add(
            PreferenceRecord(
                patient_id=MARIA,
                raw_text=SAID,
                context=CONTEXT,
                status="extracted",
                hard_constraints=extracted.get("hard_constraints"),
                soft_preferences=extracted.get("soft_preferences"),
                expiry=extracted.get("valid_until"),
                contact_preferences=extracted.get("contact_preference"),
                notify_if_opens=bool(extracted.get("notify_if_opens")),
                requested_time=extracted.get("requested_time"),
                raw_extraction=extracted,
            )
        )

        db.add(
            PreferenceRecord(
                patient_id=TOM,
                raw_text=TOM_SAID,
                status="extracted",
                hard_constraints=TOM_EXTRACTION["hard_constraints"],
                soft_preferences=TOM_EXTRACTION["soft_preferences"],
                expiry=None,
                contact_preferences=TOM_EXTRACTION["contact_preference"],
                notify_if_opens=True,
                requested_time=None,
                raw_extraction=TOM_EXTRACTION,
            )
        )

        # The slot Maria wants: real, and taken by someone else. This is what
        # gets cancelled during the demo.
        db.query(Appointment).filter(
            Appointment.provider == "Dr. Patel", Appointment.start_time == monday
        ).delete()
        slot = Appointment(
            customer_id="existing-patient-77",
            service="Follow-up Consultation",
            provider="Dr. Patel",
            start_time=monday,
            duration_minutes=45,
            price=120.0,
            status="booked",
        )
        db.add(slot)
        db.commit()
        db.refresh(slot)

        print(f"  intent stored for {MARIA} (source: {source})")
        print(f"  intent stored for {TOM} (fixed: weaker match, no expiry)")
        print(f"    notify_if_opens={extracted.get('notify_if_opens')} "
              f"requested_time={extracted.get('requested_time')} "
              f"expires={extracted.get('valid_until')}")
        print(f"  contested slot id={slot.id}: Dr. Patel {monday:%A %Y-%m-%d %H:%M} "
              f"(booked by existing-patient-77, ${slot.price:.0f})")
        print(f"\n  demo: POST /api/recovery/from-cancellation {{\"slot_id\": {slot.id}}}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
