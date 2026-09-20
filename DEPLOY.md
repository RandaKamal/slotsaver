# Deploying SlotSaver to DigitalOcean

Written for: whoever on the team is running the deploy (Kevin, Randa, Zaid).

Target is **App Platform**, one app, two components, one origin:

```
https://<app>.ondigitalocean.app/            -> web  (Next.js)
https://<app>.ondigitalocean.app/api/...     -> api  (FastAPI)
https://<app>.ondigitalocean.app/health      -> api
https://<app>.ondigitalocean.app/playground  -> api
```

Running both behind one hostname is the whole trick. It makes the frontend's
API calls same-origin, which means **CORS stops mattering** and
**`NEXT_PUBLIC_API_URL` no longer has to be baked in at build time** — the two
problems the handoff flagged as landmines. It also gives the ElevenLabs webhook
tools one stable HTTPS base URL.

Running cost: ~$22/month (api 1GB $10 + web 0.5GB $5 + dev Postgres $7).

---

## 0. Prerequisites

```bash
# macOS/Linux: brew install doctl     Windows: winget install DigitalOcean.Doctl
doctl auth init                        # paste a DO API token
doctl account get                      # should print your account
```

The app deploys from GitHub (`RandaKamal/slotsaver`, branch `main`), so
**DigitalOcean needs access to that repo**. First `doctl apps create` will fail
with a repo-access error until you authorise the DigitalOcean GitHub app at
<https://cloud.digitalocean.com/apps/github/install>. Randa owns the repo, so
she may have to click it.

---

## 1. Create the app

```bash
doctl apps create --spec .do/app.yaml
doctl apps list                        # note the app id and the live URL
```

This provisions the managed Postgres too. First build takes ~5–10 min.

## 2. Put the real secrets in

`.do/app.yaml` ships `CHANGE_ME` placeholders — real keys are never committed.
Set them in the control panel: **Apps → slotsaver → api → Settings →
Environment Variables**, encrypted:

`NVIDIA_API_KEY`, `ELEVENLABS_API_KEY`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, and (benchmark only) `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`.

The non-secret ids — agent ids, phone number id, `DATABASE_URL`,
`BACKEND_BASE_URL`, `CORS_ALLOW_ORIGINS` — are already in the spec and need no
action.

> ⚠️ **After this step, never re-apply `.do/app.yaml` blind.** It would
> overwrite every real key with `CHANGE_ME`. To change the spec later, pull the
> live one first:
> ```bash
> doctl apps spec get <app-id> > .do/live.yaml   # gitignored, has real values
> # edit .do/live.yaml, then:
> doctl apps update <app-id> --spec .do/live.yaml
> ```

## 3. Seed the demo data

The schema builds itself on boot (`create_all` + `ensure_columns` in
`app/main.py`), but the database starts empty. Seed it from your laptop —
`DATABASE_URL` as a real env var overrides the `.env` value:

```bash
# Connection string: DO control panel -> Databases -> db -> Connection details
DATABASE_URL='postgresql://...?sslmode=require' python scripts/seed_demo_data.py
```

Re-run this before any demo; it clears and re-seeds every time.

## 4. Repoint the ElevenLabs webhook tools  ← do not skip

The five `*_call` webhook tools currently point at a `trycloudflare.com` tunnel
on Kevin's laptop. Until you repoint them the agent will talk normally and then
**every tool call fails mid-call** — it just goes quiet.

```bash
python scripts/update_call_tool_urls.py https://<app>.ondigitalocean.app
```

These tools are **global to the ElevenLabs account, not per-environment.**
Pointing them at production breaks local call testing, and pointing them back at
a tunnel takes production down. Whoever runs it last wins — say so in the team
chat.

## 5. Verify

```bash
APP=https://<app>.ondigitalocean.app
curl -s $APP/health                                  # {"status":"ok"} or similar
curl -s $APP/api/appointments | head -c 300          # seeded slots, NOT 404
curl -s -o /dev/null -w '%{http_code}\n' $APP/       # 200, dashboard loads
```

A **404 on `/api/...` while `/health` works** means `preserve_path_prefix` got
lost from the ingress rules — App Platform is stripping `/api` and FastAPI sees
`/voice/book` instead of `/api/voice/book`.

Then in the browser: open the dashboard, confirm it renders live data (no
console CORS errors, no calls to `localhost:8000`), cancel a slot, and check a
ranked replacement appears for approval.

Last, test the call path **with the sandbox agent, not by phoning anyone** —
workflow is in `HANDOFF.md`.

---

## Redeploying

`deploy_on_push: true` is set, so a push to `main` redeploys both components
automatically. Manual: `doctl apps create-deployment <app-id>`.

Rollback: **Apps → slotsaver → Activity →** pick the last good deployment →
*Rollback*. The database is not rolled back with it.

## Things that will still bite you

- **Twilio is a trial account.** Outbound calls play "press any key to
  continue" first, and only numbers verified in the Twilio console can be
  called. Not disableable via API — upgrading (small top-up) is required before
  demoing to anyone else's phone.
- **The ElevenLabs API key has been exposed in chat transcripts.** Rotating it
  is overdue. Deploying puts it on a server, which is a reasonable moment to do
  it: rotate in the ElevenLabs dashboard, update the env var in step 2, redeploy.
- **The dev Postgres is not backed up.** Fine for demo data you can reseed in
  one command; not fine for anything you care about.
- **A deploy does not reseed.** The data survives deploys now (that was the
  point), but if you wipe it you are back to step 3.

## Reproducing production locally

```bash
docker compose up --build     # Postgres + both images, same Dockerfiles
```

Use this to catch Postgres-only breakage before it reaches the deployed app.
The plain `uvicorn` / `next dev` loop in `HANDOFF.md` is still faster for
day-to-day work.
