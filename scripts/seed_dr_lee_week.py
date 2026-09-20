"""Seeds one full week of Dr. Lee's calendar for the live rearrangement demo.

Run from the repo root:
    python scripts/seed_dr_lee_week.py

This is only a runner. The seed itself lives in
apps/api/app/db/seed_dr_lee_week.py so the CLI and the /api/dev/seed endpoint
share one definition - this file used to carry its OWN copy of the logic, and
the copies drifted: the one here never cleared outreach_attempts or
recovery_plans, so every run left the stale rows that make
_contact_history report "we keep pestering this patient" until
decide_outreach answers should_call=false and no call goes out at all.

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
4. Friday 4:45 PM opens -> the only remaining eligible candidate (Kevin) is a
   weak match (flexible, no strong time preference) - the offer times out,
   the queue exhausts, and the incentive fallback kicks in automatically.
   Kevin is also written as a customer who hasn't been in for months and
   mentions his son Max - stored preference text the phone agent can draw
   on for a personal, relationship-building call, not just a slot pitch.

Nothing about steps 2-4 is scripted UI behavior - it is the real
ranking/matching/incentive pipeline reacting to real stored data, exactly as
it would for any other cancellation.
"""

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from app.db.seed_dr_lee_week import seed_dr_lee_week  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed_dr_lee_week(db)
    finally:
        db.close()

    print(
        "cleared {cleared_appointments} appointments, "
        "{cleared_preferences} preference records, "
        "{cleared_outreach_attempts} outreach attempts, "
        "{cleared_recovery_plans} recovery plans".format(**result)
    )
    print(
        "seeded {seeded_appointments} appointments, "
        "{seeded_preferences} preference records".format(**result)
    )
    print("Cancel Tuesday 10:00 AM live to start the chain.")


if __name__ == "__main__":
    main()
