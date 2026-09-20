"""One-off demo seeding trigger, so the Dr. Lee rearrangement scenario can be
loaded into whatever database this deployment's DATABASE_URL points at
without needing that connection string on a local machine.

Destructive (clears and replaces all appointments/preference_records) and
deliberately unauthenticated, consistent with the rest of this hackathon
demo API (e.g. /api/outreach/{id}/approve already places a real phone call
with no auth). Safe to delete this route (and app/db/seed_dr_lee_week.py)
once the demo no longer needs re-seeding on demand.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.seed_dr_lee_week import seed_dr_lee_week

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/seed-dr-lee-week")
def seed_dr_lee_week_route(db: Session = Depends(get_db)) -> dict:
    return seed_dr_lee_week(db)
