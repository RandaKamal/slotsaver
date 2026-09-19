"""Owner: Randa. Seeds the SQLite database with demo appointment slots.

Run from anywhere, e.g. from the repo root:
    python scripts/seed_demo_data.py

Clears and re-seeds the appointments table every run, so it's safe to use
before each demo/test pass.
"""

import sys
from pathlib import Path

# scripts/seed_demo_data.py -> repo root -> apps/api (where the `app` package lives)
_API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from datetime import datetime, timedelta  # noqa: E402

from app.db.models.appointment import Appointment  # noqa: E402
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


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        deleted = db.query(Appointment).delete()
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
        db.commit()
        print(f"cleared {deleted} existing rows, seeded {len(SLOTS)} appointment slots")
    finally:
        db.close()


if __name__ == "__main__":
    main()
