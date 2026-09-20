# Demo Flow

Step-by-step walkthrough of the live demo scenario.

---

## The Maria scenario — cancellation recovery (the actual pitch)

Booking is table stakes. This is the part that only works because intent is stored.

### Setup

```bash
python scripts/seed_demo_data.py       # 8 clinic slots
python scripts/seed_demo_scenario.py   # Maria's intent (real Nemotron call) + the contested slot
```

Prints the contested slot id — slot 9 below.

### The story

**1. A call that a normal booking agent loses.**
Maria wants Dr. Patel, Monday 6pm. That slot is taken. A booking agent says
"nothing available" and the call ends: the patient is gone and the slot is
still going to sit empty if it ever frees up. Two losses from one call.

SlotSaver instead stores her *intent*, extracted by Nemotron from what she said:

```
notify_if_opens : true          <- she asked to be told
requested_time  : 18:00
preferred_provider: Dr. Patel   <- recovered from EARLIER in the call, not this sentence
excluded_days   : Tue..Sun      <- "only Monday" inverted into six exclusions
expiry          : 2026-09-21    <- "after that I fly back to Germany"
```

**2. Someone cancels that exact slot.**

```bash
curl -X POST localhost:8000/api/recovery/from-cancellation \
  -H 'Content-Type: application/json' -d '{"slot_id": 9}'
```

```
CANCELLED : existing-patient-77 gave up Dr. Patel 2026-09-21T18:00
AT RISK   : $120
NEMOTRON RANKING:
  maria-k   0.96  Prefers Dr. Patel and 6 pm slot; matches exactly.
  tom-r     0.32  Prefers mornings; slot is evening, less ideal.
```

$120 that was about to evaporate, routed to the one patient it fits — a patient
the clinic had already told "no availability" and would otherwise never call back.

### The contrast that proves it isn't the LLM guessing

Cancel a *Tuesday* slot instead (`slot_id: 6`) and the same two patients produce
a different, correct answer:

```
EXCLUDED : maria-k — "Tuesday is excluded"
  tom-r   0.95  Prefers mornings, slot at 11am matches, any provider okay.
```

Maria is removed by **deterministic code** in `app/services/recovery_matcher.py`,
before Nemotron sees the pool. Hard constraints, expiry, and provider insistence
are never the model's decision, so it cannot talk its way past them. Nemotron
ranks; it does not gatekeep.

### What to say out loud

- The slot was filled *because the patient's constraints were remembered*, not
  because someone happened to call back at the right moment.
- The expiry matters: Monday is her last useful day. A day later this same match
  is worthless, and the system knows that.
- Same system, same two patients, two slots, two different right answers.
