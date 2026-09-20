"""The active business's incentive policy - what Nemotron's incentive
decision (see app/agents/nemotron/incentive.py) is allowed to choose from,
and what recovery_service's deterministic backstop checks it against.

This used to be a single hardcoded module-level dict. It now lives on the
active BusinessProfile row (app/db/models/business_profile.py) so a dental
clinic, a tutoring center and a barber shop can each run their own policy
without a code change; `get_business_policy` is a thin re-export so existing
callers (recovery.py, recovery_scheduler.py, outreach_service.py) only need
to pass in a DB session, same as before.
"""

from app.services.business_profile_service import get_business_policy

__all__ = ["get_business_policy"]
