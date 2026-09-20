# Deploying SlotSaver — free stack

Written for: whoever on the team is running the deploy (Kevin, Randa, Zaid).

Everything below costs **$0** and needs **no credit card**.

| Piece | Where | Why there |
|---|---|---|
| Frontend (Next.js) | **Vercel** Hobby | Free, built for Next.js, preview deploy per PR |
| API (FastAPI) | **Render** free web service | Free, and a *real container* — see below |
| Database | **TigerData** (MLH perk) | Free Postgres, $1,000 credit |

> **Why the API can't be serverless.** `voice.py` hands ~12s of extraction and
> ~20–30s of recovery work to `BackgroundTasks` that run *after* the response
> is sent — that is what makes the voice turn 0.027s instead of 12.75s, and
> what makes a cancellation queue its own replacement. Serverless platforms
> (Vercel Functions, Cloud Run scale-to-zero) freeze the instance when the
> response returns, so that work is silently dropped. Nothing errors; the
> demo just quietly stops working. Render runs a persistent container.

**DigitalOcean is not in this stack.** A DO account cannot create any resource
until a payment method is added, and the signup credit is $5 scoped to
Inference Cloud, which does not cover App Platform. `.do/app.yaml` is kept in
the repo as a paid alternative (~$10/mo) if you ever want it.

---

## 1. Database — TigerData

1. Sign up at <https://mlh.link/tigerdata> — **$1,000 credit, valid 30 days.**
2. Create a PostgreSQL service in a **US East** region (Render runs in Ohio; a
   west-coast database adds a round trip to every query).
3. Copy the connection string:
   ```
   postgres://tsdbadmin:<pw>@<host>.tsdb.cloud.timescale.com:<port>/tsdb?sslmode=require
   ```

TigerData is plain PostgreSQL (Timescale's rebrand), so nothing in the app
changes. The `postgres://` scheme it hands out is normalised to `postgresql://`
in `app/db/session.py`, since SQLAlchemy 2.x rejects the short form.

## 2. API — Render

**Dashboard → New → Blueprint → select this repo.** It reads `render.yaml`.

Render prompts for every `sync: false` value. Two you won't have yet:

- `CORS_ALLOW_ORIGINS` — the Vercel URL. Put a placeholder now, fix in step 4.
- `BACKEND_BASE_URL` — this service's own URL, shown once created.

Set `DATABASE_URL` to the TigerData string from step 1. **The service will
refuse to boot without it** — `REQUIRE_POSTGRES` makes a missing value a loud
crash instead of a silent fallback to a SQLite file that Render wipes on every
restart.

Note the service URL: `https://slotsaver-api.onrender.com` (or similar).

## 3. Seed the demo data

The schema builds itself on boot. The database starts empty:

```bash
DATABASE_URL='postgres://tsdbadmin:...?sslmode=require' python scripts/seed_demo_data.py
```

Needs `psycopg2-binary` locally — already in `apps/api/requirements.txt`.
Re-run before any demo; it clears and re-seeds every time.

## 4. Frontend — Vercel

**New Project → import this repo**, then in project settings:

- **Root Directory:** `apps/web`  ← required, this is a monorepo
- **Environment Variables:**
  - `NEXT_PUBLIC_API_URL` = the Render URL from step 2
  - `NEXT_PUBLIC_ELEVENLABS_AGENT_ID` = `agent_2801m2xmgxn0ezhvwewp08yzrphz`

`NEXT_PUBLIC_*` is inlined at **build** time, so changing it later needs a
redeploy, not just an env edit. If you forget it entirely the production build
**fails on purpose** with a message telling you this — better than shipping a
dashboard that fetches itself and renders nothing.

Then go back to Render and set `CORS_ALLOW_ORIGINS` to the Vercel URL for real.
Frontend and API are on different origins now, so without this the browser
blocks every request.

## 5. Repoint the ElevenLabs webhook tools  ← do not skip

The five `*_call` webhook tools still point at a `trycloudflare.com` tunnel on
Kevin's laptop. Until you repoint them the agent talks normally and then
**every tool call fails mid-call** — it just goes quiet.

```bash
python scripts/update_call_tool_urls.py https://slotsaver-api.onrender.com
```

Point them at the **Render** URL, not the Vercel one — the tools call the API.

These tools are **global to the ElevenLabs account, not per-environment.**
Pointing them at production breaks local call testing and vice versa. Whoever
runs it last wins, so say so in the team chat.

## 6. Keep Render warm before demoing  ← matters more than it sounds

**Render's free tier spins down after 15 minutes without inbound traffic, and
takes ~1 minute to wake.** During a live call that is a full minute of silence
while a judge watches. The background tasks themselves are safe (they finish in
~30s, well inside the 15-minute window) — the risk is purely the first request
after an idle spell.

Set up a free pinger before demo day: <https://cron-job.org> or UptimeRobot,
hitting `https://slotsaver-api.onrender.com/health` every 10 minutes.

Free tier gives 750 instance hours/month and a month is ~744 hours, so one
always-warm service fits — just barely, and only one.

## 7. Verify

```bash
API=https://slotsaver-api.onrender.com
curl -s $API/health                              # ok
curl -s $API/api/appointments | head -c 300      # seeded slots, not []
```

Then in the browser, on the Vercel URL: dashboard renders live data, **no CORS
errors in the console**, cancel a slot, confirm a ranked replacement appears
for approval.

Last, test the call path **with the sandbox agent, not by phoning anyone** —
workflow is in `HANDOFF.md`.

---

## Redeploying

Both platforms auto-deploy on push to `main`. Render: `autoDeploy: true` in the
blueprint. Vercel: default for the production branch, plus a preview URL per PR.

## Things that will still bite you

- **The Render cold start** (see step 6). The single most likely thing to
  embarrass you on stage.
- **The TigerData credit expires 30 days after signup**, and nothing is backed
  up. Fine for demo data you can reseed in one command.
- **Twilio is a trial account.** Outbound calls play "press any key to
  continue" first, and only numbers verified in the Twilio console can be
  called. Not disableable via API — upgrading is required before demoing to
  anyone else's phone.
- **The ElevenLabs API key has been exposed in chat transcripts.** Rotating it
  is overdue, and deploying puts it on a server — a reasonable moment to do it.
- **Render's filesystem is ephemeral.** Irrelevant here (everything lives in
  TigerData) but do not write files expecting them to persist.

## Reproducing production locally

```bash
docker compose up --build     # Postgres + both images, same Dockerfile as Render
```

Catches Postgres-only breakage before it ships. The plain `uvicorn` / `next dev`
loop in `HANDOFF.md` is still faster day to day.

## Paid alternative: DigitalOcean App Platform

`.do/app.yaml` deploys both components to one DO app behind a single origin
(~$10/mo, needs a card). That layout has a real advantage — same origin means
no CORS and no build-time API URL — so it is worth knowing about if the free
tiers get annoying. `doctl apps create --spec .do/app.yaml`.
