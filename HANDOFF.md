# SlotSaver — session handoff

Written for: the next Claude Code session picking this up.
Last updated: 2026-09-20, at commit `1aa5856` on `main`.

## Next task: deploy to DigitalOcean

Everything below is context. The immediate job is deployment. Read
**Deployment notes** first — several things are currently localhost-only or
tunnel-dependent and will break in production.

---

## What SlotSaver is

Autonomous cancellation-recovery for medical clinics. It stores scheduling
INTENT (hard constraints + soft preferences), so when an appointment is
cancelled it already knows who wants that slot, ranks them, and phones the best
match — with an owner approving each call.

The loop, end to end, all of it working:

```
patient cancels (voice or dashboard)
  -> slot freed atomically
  -> deterministic eligibility filter        recovery_matcher.py
  -> Nemotron ranks survivors                ranker.py
  -> Nemotron: is this call worth making?    outreach.py decide_outreach
  -> Nemotron drafts tone + talking points   outreach.py generate_call_brief
  -> queued for OWNER APPROVAL               dashboard, nothing dials yet
  -> owner approves
  -> ElevenLabs phones the patient           call_service.place_call
  -> agent books / cancels / saves preferences live
```

## Team ownership

- **Kevin (the user)** — Nemotron: prompts, extraction, ranking, incentive
  selection, reasoning, benchmark. Owns `app/agents/**` and the phone prompt.
- **Randa** — ElevenLabs integration, backend plumbing, DB-backed execution,
  deterministic safeguards. Branch: `elevenlabs-integration`.
- **Zaid** — production UI. Branch: `feature/ui`.

Push to `main` and `feature/ai-recovery-playground` (kept identical). Randa
branches off `main`, so merge her work in rather than rebasing hers.

---

## Live external resources (already configured, do not recreate)

| Thing | ID |
|---|---|
| Browser agent (web widget, 3 client tools) | `agent_2801m2xmgxn0ezhvwewp08yzrphz` |
| Phone agent (telephony, 5 webhook tools) | `agent_0101m2yctba3fgcadx5daphpfv2c` |
| Sandbox agent (prompt testing, mockable tools) | `agent_6001m2yfa42nepgaea8pbn3t78zy` |
| Twilio number in ElevenLabs | `phnum_5001m2ybj5q6f62r60s66r7a1kbz` (+15722348213) |

**Two agents on purpose.** ElevenLabs rejects a conversation override naming
tools not already attached to the agent, and the browser SDK's override type has
no `tool_ids` field at all — only `prompt` and `llm`. So the browser keeps
client tools (executed in the page) and telephony gets its own agent with
webhook tools. Do not try to merge them back into one.

Webhook tool IDs are listed in `scripts/update_call_tool_urls.py`.

---

## Deployment notes

**The deploy is prepared but not yet executed.** Everything in the repo is
ready; someone still has to run it against a DigitalOcean account. The runbook
is `DEPLOY.md` — follow that, not this section.

Shape: App Platform, one app, two components behind one hostname
(`/` -> web, `/api` -> api), managed Postgres, spec in `.do/app.yaml`.

Status of the four landmines this section used to list:

1. **Webhook tools still point at the cloudflare tunnel.** Unchanged and still
   the biggest trap — `python scripts/update_call_tool_urls.py https://<prod>`
   is step 4 of `DEPLOY.md`. The script now refuses a non-HTTPS URL.
2. **SQLite is gone in production.** App Platform has no persistent disks, so
   it was never survivable there. The database is TigerData (PostgreSQL, via
   the MLH perk at mlh.link/tigerdata — $1,000 of credit, **expiring 30 days
   after signup**), set as a `DATABASE_URL` secret rather than provisioned by
   the spec. `app/db/migrate.py` now renders DDL per dialect. SQLite is still
   the local default.
3. **CORS is no longer hardcoded.** Dev origins are built in, extras come from
   `CORS_ALLOW_ORIGINS`. In production it is moot — same origin.
4. **`NEXT_PUBLIC_API_URL` no longer needs to be baked in.** Unset, the client
   uses same-origin relative paths (`apps/web/lib/constants.ts`). Only set it
   if web and api are ever split into separate apps.

Still true and still worth reading:

5. **Secrets.** `.env` is gitignored. `.do/app.yaml` carries `CHANGE_ME`
   placeholders, so re-applying it blind wipes the real keys — pull the live
   spec first (`doctl apps spec get`). The ElevenLabs key has been exposed in
   chat transcripts more than once; rotating it is overdue, and Kevin has
   repeatedly deprioritised it — raise it once, respect the answer.
6. **Twilio is still a TRIAL account.** Every outbound call plays "press any key
   to continue" first, and only numbers verified in the Twilio console can be
   called. This cannot be disabled via API. Upgrading (a small top-up) removes
   both limits and is required before demoing to anyone else's phone.

Not verified: nothing has been run against a real Postgres server. The schema
was compiled offline against the PostgreSQL dialect and the models are all
portable ORM types, but first contact with the managed database is still ahead.

---

## Verified working (do not re-litigate)

- Outbound call connects, agent speaks Nemotron's brief, books, cancels,
  reschedules and saves preferences mid-call — all against the real DB.
- Cancellation closes the loop by itself: freeing a slot queues a ranked
  replacement for approval with no human involvement.
- Randa's incentive fallback: decline x3 → exhausted → Nemotron picks from the
  approved list → deterministic policy check (approved list, excluded services,
  revenue floor) → re-offer. Survives a server restart.
- Double-booking is impossible: atomic UPDATE guarded on the current status.
  Tested with 12 concurrent bookings → exactly 1 winner, 11 rejected with 409.
- Patient-side cancel is ownership-pinned (403 if not yours); clinic-side cancel
  deliberately is not.
- Async extraction: the voice turn waits **0.027s**, down from **12.75s**.

## Known broken / unfinished

- **Hindi extraction fails reproducibly** — Nemotron returns empty/non-JSON
  after retries. Raw input is preserved and it fails safely. Unexamined, and in
  Kevin's area (extraction prompt).
- **Browser agent prompt still advertises** English/Spanish/Arabic/German while
  the configured presets are Arabic/Hindi. The phone prompt no longer mentions
  languages at all. Align before demo.
- **Frontend is weak** — Kevin's words: "very bad right now".
- **Inbound calls have no patient identification.** `patient_id` comes from the
  outbound call's dynamic variables. A patient dialling in is unidentified;
  caller-ID lookup against `PreferenceRecord.phone_number` is the obvious fix.
- `recent_declines` in contact-fatigue scoring is hardcoded to 0 — it needs a
  real call-outcome webhook to ever be non-zero.

---

## The benchmark: be careful here

Kevin wants to "beat metrics against Claude and Gemini". **The current benchmark
cannot support that claim and should not be used for it.**

It is N=5, and the same author (Claude, in earlier sessions) wrote the
scenarios, the ground-truth labels, AND the prompt being graded. While building
the extraction A/B, **two of three apparent model failures turned out to be
wrong labels, not model errors.** Across three identical runs Gemini scored
100%, 20%, 100% — variance larger than any gap being claimed.

Tuning Nemotron does not fix this; the measuring instrument is broken. Either
get Randa and Zaid to blind-label 30–50 fresh cases independently, or drop the
comparison and lead with the latency result (12.75s → 0.027s), which is
measured, reproducible and uncontested.

This has been raised with Kevin several times and he has not disagreed, but he
keeps restating the goal. State the position once, clearly, then follow his
decision.

---

## Testing the phone agent without calling Kevin

He is tired of being phoned for tests. Use the sandbox agent.

`simulate-conversation` cannot drive the production phone agent — it refuses
rather than supplying the `patient_id` dynamic variable the webhook tools
require. The sandbox agent has the same prompt with placeholders filled in and
client-tool twins of the same five tools, so `tool_mock_config` works.

Workflow: edit `apps/api/app/agents/prompts/phone_agent.md` → patch the sandbox
with placeholders filled → simulate → when it behaves, run
`python scripts/sync_phone_agent.py` to push to production.

**Verbosity baseline**: a real call averaged 35.6 words per agent turn and Kevin
interrupted with "you are going in too long". It is now 11.2. Above ~20 is a
regression worth catching before it reaches a live call.

---

## Running locally

```bash
cd apps/api && python -m uvicorn app.main:app --port 8000 --reload
cd apps/web && npm run dev                      # :3000
python scripts/seed_demo_data.py                # fresh demo data
cloudflared tunnel --url http://localhost:8000  # only needed for real calls
python scripts/update_call_tool_urls.py https://<new-url>
```

Windows notes: kill stale servers with `taskkill //F //PID <pid>`; plain `kill`
often does not work. Native Windows Python cannot read `/tmp` paths — use the
scratchpad directory instead.

---

## Remaining roadmap (Kevin's list, his ordering)

1. **Deploy to DigitalOcean** ← current task
2. Payment plan
3. Improve the Nemotron harness
4. Improve the frontend
5. Beat a metric vs Claude/Gemini (see caveat above)
6. Better context extraction for Gemini capabilities
7. A single 2-minute judge flow combining visual slot arrangement and a live
   call with incentives

Claude previously suggested frontend → judge flow → deploy → harness, since the
judge flow determines what the frontend must support. Kevin chose deploy first.
Follow his ordering.

## How Kevin works

Direct, moves fast, tests on real hardware, and reports honestly what broke. He
values being told when something is wrong more than being agreed with — several
real bugs in this project were found because he pushed back on a claim. Give him
the verdict first, evidence second, and do not pad.
