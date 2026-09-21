# SlotSaver — AI cancellation recovery for appointment businesses

A last-minute cancellation is a slot that will almost certainly go unfilled. Waitlists
answer "who is free?", which is the wrong question — most people on a waitlist do not
want *that* Tuesday at 10am. SlotSaver remembers what each customer actually said they
wanted, ranks the people the freed slot genuinely suits, and phones them until someone
takes it.

> A waitlist stores availability. SlotSaver remembers scheduling intent — and acts on it.

🎥 **[Demo video](docs/slotsaver.mp4)** · 🚀 **[Live app](https://slotsaver-smoky.vercel.app)**

---

## What happens when someone cancels

Nothing here is a button an owner has to press. One cancellation starts the whole chain:

1. **The slot frees.** The cancellation is recorded and the slot is claimed for planning
   (so two triggers can't both start ranking it).
2. **Ineligible customers are filtered out** — deterministically, before any model runs.
3. **Nemotron ranks the rest** against their stored preferences, and explains each score.
4. **Candidate 1 is called at full price.** A voice agent offers them the slot.
5. **They say no.** The call ends; the outcome is read back from ElevenLabs and the queue
   advances on the real result, not a blind timeout.
6. **Candidate 2 is called with an incentive** — chosen by Nemotron from the business's
   approved list, then checked against its caps by deterministic code.
7. **Candidate 3 escalates**, because a refused incentive is evidence the next offer has
   to be worth more than the one just turned down.
8. **Someone accepts and the slot is rebooked atomically.** If they were already booked
   elsewhere, that move frees *their* old slot, and recovery starts on it too.

Step 8 is the part that compounds: recovery is recursive, so one cancellation can
rearrange a whole day into a better fit for everyone in it.

## The division of labour

The model decides; deterministic code validates and executes. That line is deliberate and
it is load-bearing.

| | Nemotron decides | Backend enforces |
|---|---|---|
| Ranking | who fits the slot, and why | who is *eligible* at all |
| Incentives | which offer to make | discount cap, revenue floor, excluded services, time window |
| Outreach | whether a call is worth placing | contact fatigue, whether a number exists |
| Booking | — | the atomic `available → booked` update |

A model that hallucinates a customer, picks a 90% discount, or ranks nobody cannot break
the system — every one of those paths has a guard that fails closed. The booking itself is
a single `WHERE id = ? AND status = 'available'` update, so two people accepting the same
slot cannot both win.

## Architecture

**Voice — ElevenLabs.** Two agents: a browser widget that captures scheduling intent from
a natural conversation, and a phone agent with webhook tools for outbound calls over
Twilio.

**Decision — NVIDIA Nemotron.** Intent extraction, candidate ranking with explanations,
incentive selection, and the call script. Rate limits are per-model, so the client falls
back down a model chain rather than failing the recovery.

**Recovery engine — FastAPI.** An autonomous scheduler ticks every few seconds and does
the cheap jobs first: resolve finished calls, expire stale offers, apply the incentive
round, then plan new cancellations. Planning is the slow job, so it runs last — otherwise
one throttled ranking starves everything behind it.

## Running it locally

**Requirements:** Python 3.11+, Node 18+, and API keys for NVIDIA and ElevenLabs. Calls
also need Twilio.

```bash
git clone <repo> && cd slotsaver
cp .env.example .env          # fill in the keys you have
```

**API** — from `apps/api`:

```bash
python -m venv venv && ./venv/Scripts/python.exe -m pip install -r requirements.txt
./venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

**Frontend** — from `apps/web`:

```bash
npm install && npm run dev
```

**Seed a week of demo data** (one provider, Monday–Friday, with stored preferences that
make the rearrangement chain fire):

```bash
python scripts/seed_dr_lee_week.py
```

It clears appointments, preferences, outreach attempts *and* recovery plans. That last
part matters: stale outreach rows read as "we keep pestering this customer" and the system
will correctly decide to stop calling anyone.

Then open the calendar, cancel the Tuesday 10am appointment, and watch the chain run.

## Configuration

Everything business-specific lives in a database-backed profile, not in the code — the
same app runs a dental clinic, a tutoring centre, or a barber shop. It sets the worker /
customer / service vocabulary, opening hours, booking rules, and:

```jsonc
{
  "auto_call_enabled": true,      // the owner opts into autonomous calling
  "incentive_from_attempt": 2,    // call 1 is full price; discounts start at call 2
  "candidate_timeout_seconds": 120,
  "max_recovery_attempts": 5
}
```

Incentive policy — allowed types, maximum discount, minimum revenue, excluded services,
eligible time window — is enforced by code on every offer, whatever the model proposes.

## Tests

```bash
cd apps/api && ./venv/Scripts/python.exe -m pytest tests/ -q
```

Covers the call flow end to end: a declined call advancing the queue, an uncallable
candidate being skipped rather than waited out, the incentive round attaching to the right
attempt, and the queue clamping instead of running off the end of the candidate list.

## Known limitations

- **The booking webhook needs a public URL.** ElevenLabs calls the agent's booking tool
  from their cloud, so it cannot reach a laptop. Running locally, that tool fails — so the
  system reads the call transcript back and makes the booking server-side instead. A
  customer who agreed is always booked; use a tunnel (`cloudflared tunnel --url
  http://localhost:8000`) plus `scripts/update_call_tool_urls.py` if you want the tool
  itself to succeed.
- **A Twilio trial allows one concurrent call** and only to verified numbers. Set
  `DEMO_CALL_OVERRIDE_NUMBER` so every match dials the one handset you verified.
- **Planning takes 20–40 seconds**, occasionally longer when NVIDIA throttles. It is three
  sequential model calls — rank, worth-calling, call script. The cancellation itself
  returns in milliseconds; only the outbound call waits.

## Layout

```text
apps/api     FastAPI backend — recovery engine, agents, scheduler
apps/web     Next.js dashboard — calendar, recovery panel, settings
scripts/     seeding, benchmarks, ElevenLabs tool configuration
docs/        architecture, API, benchmark methodology, decisions
```

Further reading: [`docs/architecture.md`](docs/architecture.md),
[`docs/decisions.md`](docs/decisions.md), [`docs/benchmark.md`](docs/benchmark.md),
[`docs/twilio-integration.md`](docs/twilio-integration.md).

## Stack

Next.js · TypeScript · CSS Modules (Tailwind configured) · FastAPI · SQLAlchemy ·
SQLite / Postgres · NVIDIA Nemotron · ElevenLabs · Twilio
