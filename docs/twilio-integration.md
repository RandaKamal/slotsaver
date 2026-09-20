# Outbound recovery calls: decision pipeline + Twilio integration

## What exists now

`POST /api/recovery/from-cancellation` does more than rank candidates. For the
top-ranked candidate it runs a full decision pipeline and queues a call for
owner approval — nothing dials automatically.

```
cancellation
  -> recovery_matcher.find_candidates()   deterministic eligibility (existing)
  -> rank_candidates()                    Nemotron ranks survivors (existing)
  -> decide_incentive()                   Nemotron, only if match < 0.9 (existing)
  -> decide_outreach()                    NEW: is this call worth placing at all?
  -> generate_call_brief()                NEW: if yes, tone + talking points
  -> OutreachAttempt row, status=pending_approval
```

`decide_outreach()` can say no — a candidate existing in the ranking is not
consent to call them. It factors: match score, incentive cost vs. revenue at
risk, and contact fatigue (times contacted in the last 7 days, declines).
`generate_call_brief()` never decides booking logic — ElevenLabs' own tools
still confirm real availability and do the actual booking. It only decides
what the agent says on the way in: tone, opening line, key points grounded in
the patient's actual stored wording, and how to phrase an incentive if there
is one.

### Approval queue

- `GET /api/outreach/pending` — calls Nemotron thinks are worth making,
  `should_call=True`, still `pending_approval`.
- `POST /api/outreach/{id}/approve` / `/reject` — the only place a human
  decision enters. Idempotent: re-deciding an already-decided row is a 409.
- Dashboard: `components/outreach/OutreachQueue.tsx`, on the home page.

### Known gap: `recent_declines` is always 0

`outreach_service._contact_history()` counts recent contact *attempts* from
real `OutreachAttempt` rows, but has no way to know if a patient declined
*during* a call — that requires a call to have actually completed, which
needs the Twilio wiring below. It's marked with a `TODO` rather than faked.

## What Twilio needs, not yet built

**The tools are client tools today — that doesn't work for phone calls.**
`save_scheduling_intent`, `get_available_slots`, and `book_appointment` are
registered as ElevenLabs *client* tools, executed by JS in the browser
(`VoiceAgent.tsx`). A phone call has no browser. For inbound/outbound calls
over Twilio these need *server* tool equivalents — ElevenLabs calling our
backend directly over HTTP — which also means `patient_id` can no longer come
from React state; it has to come from the caller's number or be asked for.

**Recommended approach: ElevenLabs' native Twilio import**, not a custom
Media Streams bridge. Twilio Console → get a number → ElevenLabs dashboard →
Conversational AI → Phone Numbers → import via Account SID + Auth Token.
ElevenLabs configures the Twilio webhook for you.

**Outbound calls specifically** (this is what Approve triggers) use
ElevenLabs' outbound-call API, not just phone-number import: you POST to
initiate a call to `phone_number`, passing conversation overrides — this is
where `call_brief.opening_line`, `tone`, etc. get threaded through so the
agent that answers is briefed per-call, not generic.

**Local dev needs a public URL.** ElevenLabs' servers can't call
`localhost:8000` for server tools or outcome webhooks — use ngrok (or deploy)
before testing.

**Twilio trial constraint:** a free/trial account can only call verified
numbers. Fine for testing with your own phone; not fine for calling arbitrary
patients until upgraded.

### Next steps, in order

1. Get a Twilio account + number, verify your own phone in trial mode.
2. Add server-tool equivalents of the three tools (keep the client tools —
   the browser widget still needs them).
3. ngrok tunnel, import the Twilio number in ElevenLabs, point it at the agent.
4. Implement `place_call()` (stubbed as a TODO in `routes/outreach.py`) using
   ElevenLabs' outbound API, passing the stored `call_brief` as the
   conversation override.
5. Add a call-outcome webhook so `recent_declines` can finally be real.
