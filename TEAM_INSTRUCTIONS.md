# Team Instructions — Relay (AI Recovery Engine for Service Businesses)

Three developers, one repo, running Claude Code in parallel. This document is the practical
playbook: what each person builds, in what order, and how to hand off to the others without
stepping on each other's files. Read [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) first for the
ownership map this document assumes.

**Product flow:**

```text
External disruptions / cancellations / weather / traffic / live news
  → Gemini interprets the outside world
  → business state and internal context are collected
  → Nemotron acts as the recovery decision engine
  → a structured recovery plan is generated
  → actions are validated
  → calls / reschedules / notifications are executed
  → customer preferences and outcomes are stored in memory
  → future decisions improve
```

---

# Kevin

## Role
AI systems engineer and project architect. Owns repo bootstrap, the AI intelligence layer
(Gemini + Nemotron), tool use, validation, and memory.

## Responsibilities
- Initial project/repo structure.
- Gemini integration for world-understanding (structured interpretation of external disruptions).
- Nemotron integration as the recovery decision/policy engine.
- Deterministic tools the models call (never let a model invent operational facts).
- Validators that gate a `RecoveryPlan` before execution.
- Customer preference/contact memory that feeds future Nemotron decisions.
- RecoveryBench — comparative benchmark of decision quality across configurations.

## Folders owned
```text
root repo setup
apps/api/app/agents/**
apps/api/app/tools/**
apps/api/app/validators/**
apps/api/app/memory/**
docs/architecture.md
docs/benchmark.md
scripts/run_benchmark.py
```
Also allowed to modify:
```text
apps/api/app/api/routes/disruptions.py
apps/api/app/api/routes/recovery.py
apps/api/app/api/routes/execution.py
```

## Files to create initially
- `apps/api/app/agents/gemini/client.py`, `researcher.py`, `prompts.py`
- `apps/api/app/agents/nemotron/client.py`, `planner.py`, `policy_engine.py`, `prompts.py`
- `apps/api/app/agents/recovery_engine.py`
- `apps/api/app/tools/*.py` (calendar, customer, policy, notification, voice)
- `apps/api/app/validators/*.py` (policy, action, confidence)
- `apps/api/app/memory/memory_service.py`, `preference_store.py`
- `docs/architecture.md`

## Files to avoid modifying
- `apps/api/app/schemas/**` (Randa's, after agreement — coordinate first)
- `apps/api/app/db/**`, `apps/api/app/services/**`, `apps/api/app/core/**` (Randa's)
- `apps/web/**` (Zaid's)
- Any route other than `disruptions.py` / `recovery.py` / `execution.py`

## Inputs received
- Stable schemas from Randa (`Appointment`, `Customer`, `Disruption`, `RecoveryPlan`, `RecoveryAction`, `ExecutionResult`, `BusinessPolicy`).
- Service interfaces from Randa (`AppointmentService`, `CustomerService`, `CalendarService`, etc.) to build tools on top of.

## Outputs produced
- Structured disruption interpretations (Gemini output, matching `event-contracts.md`).
- Structured `RecoveryPlan` objects (Nemotron output, matching `recovery.py` schema).
- Validated, executable actions.
- RecoveryBench results (real, executed comparisons — never fabricated numbers).

## API contracts depended on
- `packages/contracts/api-contract.md`
- `packages/contracts/event-contracts.md`
- `apps/api/app/schemas/**` (as published by Randa)

## How Kevin's Claude Code agent should behave
Like an AI systems engineer and project architect. It must not randomly change frontend
implementation, database models, or shared API schemas once those contracts are established.
It should treat `apps/api/app/services/**` as a black box called only through tools.

## Gemini layer — world understanding
Interprets weather alerts, live news, traffic disruptions, business closures; identifies
business relevance; normalizes noisy external data into structured events. It does **not**
decide how customers are rescheduled — that's Nemotron's job.

Example output:
```json
{
  "event_type": "weather",
  "title": "Severe thunderstorm warning",
  "severity": "high",
  "business_relevance": 0.92,
  "start_time": "...",
  "end_time": "...",
  "summary": "...",
  "recommended_attention": "actionable"
}
```

## Nemotron layer — recovery decision engine
Receives disruption context, appointments, customer details, customer memory, available slots,
business policies, recent contact history, and appointment value/priority. Outputs a structured
`RecoveryPlan`, acting like a decision/policy engine, not a chatbot:
```json
{
  "plan_id": "plan_123",
  "confidence": 0.91,
  "actions": [
    {
      "customer_id": "customer_1",
      "appointment_id": "apt_1",
      "action_type": "offer_reschedule",
      "target_slot": "2026-09-19T14:00:00",
      "confidence": 0.94,
      "reason_codes": ["preference_match", "earlier_slot_available", "low_contact_fatigue"]
    }
  ]
}
```

## Tool use
Create deterministic tools: `get_available_slots`, `get_customer_preferences`,
`get_customer_history`, `get_business_policies`, `get_appointment_value`, `check_recent_contact`,
`create_reschedule_offer`, `schedule_customer_call`. The model must never invent operational
facts — calendar state, availability, policies, and history come only from these tools/services.

## Validators
```text
Nemotron → structured RecoveryPlan → policy validation → confidence validation
         → action validation → execution
```
Handle: policy violations, unavailable slots, excessive customer contact, low confidence,
approval-required actions. Example configurable rule:
```text
confidence >= 0.80 → eligible for auto execution
confidence < 0.80  → human approval required
```

## Memory
Preferences layer: preferred time range, preferred communication channel, free-text
constraints ("after 4 PM", "never call during work"), recent reschedule history, recent
contact frequency, customer feedback. Nemotron consumes this for future decisions.

## RecoveryBench
Once the primary flow works, compare: rules baseline, raw Nemotron, Nemotron + tools,
Nemotron + tools + memory. Metrics: policy compliance, correct action selection, preference
adherence, contact efficiency, recovery success. Execute real benchmark cases — never fabricate
numbers.

## Implementation order
1. Create repository architecture and base folders.
2. Coordinate stable contracts with Randa.
3. Create Gemini API client.
4. Build structured Gemini researcher.
5. Create Nemotron API client.
6. Define planner interface.
7. Create AI tools.
8. Generate structured RecoveryPlans.
9. Create validators.
10. Integrate memory.
11. Connect recovery routes.
12. Build RecoveryBench.
13. Optimize prompts and explainability.

## Definition of done
End-to-end flow works: external disruption → Gemini structured interpretation → business
context retrieval → Nemotron structured recovery plan → validation → approved executable
actions — output following the stable contract used by the rest of the application.

## Handoff requirements
- Publish Gemini/Nemotron output shapes to `packages/contracts/event-contracts.md` and get
  Randa's schema sign-off before wiring routes.
- Notify Zaid when `recovery.py`/`execution.py`/`disruptions.py` response shapes change.
- Log any cross-cutting contract change in `docs/decisions.md`.

---

# Randa

## Role
Backend engineer focused on clean interfaces and reliability. Owns services, schemas,
persistence, and the stable integration contracts everyone else builds against.

## Responsibilities
- FastAPI service layer (no LLM reasoning in this layer).
- Shared Pydantic schemas.
- Database models, repositories, seed data.
- Environment/configuration helpers.
- Mock-first backend so frontend and AI work can proceed in parallel.

## Folders owned
```text
apps/api/app/services/**
apps/api/app/schemas/**
apps/api/app/db/**
apps/api/app/core/**
packages/contracts/**
scripts/seed_demo_data.py
scripts/simulate_disruption.py
```

## Files to create initially
- `apps/api/app/schemas/{appointment,customer,disruption,recovery,execution,memory}.py`
- `apps/api/app/db/models/**`, `session.py`, `seed.py`, `repositories/**`
- `apps/api/app/services/{appointment,customer,disruption,calendar,notification,voice,metrics}_service.py`
- `apps/api/app/core/{config,logging,constants}.py`
- `packages/contracts/{api-contract,frontend-types,event-contracts}.md`
- `scripts/seed_demo_data.py`, `scripts/simulate_disruption.py`

## Files to avoid modifying
- `apps/api/app/agents/**`, `tools/**`, `validators/**`, `memory/**` (Kevin's)
- `apps/web/**` (Zaid's)
- Route files `disruptions.py`, `recovery.py`, `execution.py` bodies once Kevin has wired them
  (coordinate before touching)

## Inputs received
- Frontend data-shape needs from Zaid (what the dashboard needs to render).
- AI output shape requirements from Kevin (what `RecoveryPlan`/execution results must contain).

## Outputs produced
- Stable, documented schemas.
- Working database + seed data.
- Mock-first service responses that follow the final API contract.
- Published contracts in `packages/contracts/**`.

## API contracts depended on / owned
Randa is the source of truth for:
```text
GET /health
GET /api/appointments
GET /api/customers
POST /api/disruptions/analyze
POST /api/recovery/plan
POST /api/recovery/execute
GET /api/recovery/{plan_id}
GET /api/memory/{customer_id}
GET /api/metrics
```
These may initially return realistic mock data; the implementation is replaceable later
without changing the contract.

## How Randa's Claude Code agent should behave
Like a backend engineer focused on clean interfaces and reliability. Should not embed LLM
reasoning in services — that always belongs in `apps/api/app/agents/**` (Kevin's layer).

## Stable schemas
`Appointment`, `Customer`, `CustomerPreference`, `Disruption`, `RecoveryAction`, `RecoveryPlan`,
`ExecutionResult`, `DashboardMetrics`, `BusinessPolicy`. Stabilize these early so Kevin and Zaid
can build against them.

## Service abstractions
`AppointmentService`, `CustomerService`, `CalendarService`, `DisruptionService`,
`NotificationService`, `VoiceService`, `MetricsService`. The AI layer may call these; they must
never contain LLM reasoning themselves.

## Database
Demo-ready persistence for `Business`, `Customer`, `CustomerPreference`, `Appointment`,
`BusinessPolicy`, `Disruption`, `RecoveryPlan`, `RecoveryAction`, `ContactHistory`. SQLite
during hackathon development.

## Business policies
Support fields: `max_reschedules`, `minimum_notice_minutes`, `allow_auto_reschedule`,
`require_approval_for_cancellation`, `max_customer_contacts_per_day`,
`auto_execute_confidence_threshold`.

## Implementation order
1. Review the repo structure created by Kevin.
2. Implement shared schemas.
3. Create SQLite database layer.
4. Create repositories.
5. Create seed data.
6. Create service interfaces.
7. Implement mock service functionality.
8. Document API contracts.
9. Verify frontend can consume responses.
10. Expose clean interfaces for Kevin's AI layer.
11. Integrate real AI output later.

## Definition of done
- Database works; seed data works.
- Backend services return predictable objects.
- Shared schemas are stable.
- Mock responses follow the API contract.
- Kevin can plug Gemini/Nemotron into existing interfaces.
- Zaid can build without waiting for AI functionality.

## Handoff requirements
- Announce schema freeze at Checkpoint 2 (Integration Checkpoints, below).
- Provide Zaid working mock endpoints before Zaid's dashboard build starts.
- Provide Kevin service interfaces (not raw DB access) for tool-building.
- Log any schema/contract change after freeze in `docs/decisions.md`.

---

# Zaid

## Role
Frontend lead. Product-focused implementation of the dashboard, disruption view, recovery
plan UI, execution states, memory panel, and (if time permits) benchmark UI.

## Responsibilities
- Next.js/TypeScript/Tailwind frontend.
- Consume stable APIs; work initially against mock responses.
- Make disruption → recovery → execution flow visually clear and dynamic.

## Folders owned
```text
apps/web/**
```

## Files to create initially
- `apps/web/app/page.tsx`, `layout.tsx`, `dashboard/`, `disruptions/`, `recovery/`
- `apps/web/components/{dashboard,appointments,disruptions,recovery,calls,ui}/**`
- `apps/web/lib/{api,utils,constants}.ts`
- `apps/web/types/**` (mirroring `packages/contracts/frontend-types.md`)

## Files to avoid modifying
- Anything under `apps/api/**` unless coordinated with Randa/Kevin.

## Inputs received
- `packages/contracts/frontend-types.md` and `api-contract.md` from Randa.
- Mock, then real, API responses from Randa's endpoints.
- Benchmark results from Kevin (real numbers only, when available).

## Outputs produced
- Working dashboard, disruption panel, appointment schedule, recovery plan panel, execution UI,
  memory UI, and (optionally) benchmark UI.

## API contracts depended on
```text
GET /health
GET /api/appointments
GET /api/customers
POST /api/disruptions/analyze
POST /api/recovery/plan
POST /api/recovery/execute
GET /api/recovery/{plan_id}
GET /api/memory/{customer_id}
GET /api/metrics
```

## How Zaid's Claude Code agent should behave
Like a product-focused frontend engineer. Should not modify backend files unless coordinated,
and should build against the documented contract, not against backend implementation details.

## Main dashboard
Metrics: operations health, revenue protected, appointments recovered, calls made, appointments
at risk.

## Disruption panel
```text
SEVERE WEATHER WARNING
Impact window: 3:00 PM – 6:00 PM
Operational relevance: HIGH
Appointments affected: 3
Revenue exposed: $420
```

## Appointment schedule
```text
8:00 Sarah ✓
9:30 Alex ✓
11:00 Emma ✓
1:00 Priya ✓
2:00 David ✓
3:30 Emily ⚠
4:30 James ⚠
5:30 Sofia ⚠
```
Appointments should visibly transition from normal to at-risk when a disruption occurs.

## Recovery plan panel
```text
Emily
Action: Move to 2:00 PM
Confidence: 94%
Why:
✓ customer prefers afternoons
✓ earlier slot available
✓ no recent contact
```
Include Approve / Execute / Reject actions where relevant.

## Execution UI
```text
Calling Emily...
Customer answered
Alternative accepted
Calendar updated
Revenue recovered +$150
```
State transitions should feel dynamic and visually clear.

## Memory UI
```text
Emily
Prefers: Afternoons
Avoid: Before 1 PM
Preferred contact: Voice
Last rescheduled: 32 days ago
```

## Benchmark UI (time permitting)
Display actual benchmark results from Kevin: Rules Engine, Raw Nemotron, Nemotron + Tools,
Relay Full System. Never hardcode invented benchmark results.

## Implementation order
1. Dashboard shell.
2. Frontend types based on API contracts.
3. API client.
4. Appointment view.
5. Disruption card.
6. Recovery plan UI.
7. Metrics.
8. Action execution state.
9. Memory panel.
10. Benchmark UI.
11. Final demo polish.

## Definition of done
- Dashboard loads reliably; mock API data renders correctly.
- A disruption can be triggered.
- Recovery plan appears; execution state changes visibly; metrics update.
- Frontend works the same whether backend responses come from mock logic or real AI.

## Handoff requirements
- Flag to Randa any place the mock data shape doesn't match what the UI actually needs, before
  building around a workaround.
- Confirm with Kevin/Randa before Checkpoint 4–6 that UI states (calling/answered/accepted/
  updated) match the execution status values the backend will actually emit.

---

# Team-wide Claude Code rules

Every Claude Code agent on this project must follow these rules:

1. Do not refactor another developer's area without coordination.
2. Do not rename shared API fields without agreement.
3. Do not modify root configuration casually.
4. Prefer adding files inside the developer's owned folder.
5. Keep commits small and focused.
6. Preserve stable API contracts.
7. Never hardcode secrets.
8. AI models must not invent operational state.
9. Demo reliability matters more than unnecessary abstractions.
10. Avoid overengineering.
11. Every major feature should support the core demo.
12. If a change affects another developer, document it in `docs/decisions.md`.

## Git workflow
```text
feature/kevin-ai
feature/randa-backend
feature/zaid-frontend
        ↓
       dev
        ↓
       main
```

---

# Integration checkpoints

```text
Checkpoint 1: Repo structure + planning files.
Checkpoint 2: Shared schemas + mock API/service behavior.
Checkpoint 3: Frontend works against mock data.
Checkpoint 4: Gemini replaces mock disruption understanding.
Checkpoint 5: Nemotron replaces mock recovery planning.
Checkpoint 6: Execution layer integrated.
Checkpoint 7: Memory loop integrated.
Checkpoint 8: RecoveryBench integrated.
Checkpoint 9: Demo freeze.
```

Do not start implementing the full application until [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md)
and this file have been reviewed by all three developers.
