# Folder Structure — Relay (AI Recovery Engine for Service Businesses)

This document defines the repository layout, the purpose of each directory, and who owns what.
It exists so three developers (Kevin, Randa, Zaid) can use Claude Code simultaneously with
minimal merge conflicts. Read this before creating or moving any file.

## Root layout

```text
relay/
│
├── apps/
│   ├── web/                  # Next.js frontend — Zaid
│   └── api/                  # FastAPI backend + AI layer — Kevin & Randa
│
├── packages/
│   └── contracts/            # Shared API/type contracts — Randa (Kevin & Zaid consume)
│
├── docs/                     # Architecture, demo flow, decisions log
├── scripts/                  # Demo data seeding, benchmark runner, disruption simulator
├── tests/                    # Cross-cutting/integration tests (repo root level)
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── FOLDER_STRUCTURE.md
└── TEAM_INSTRUCTIONS.md
```

---

## Full tree

```text
apps/
│
├── web/                                    [OWNER: Zaid]
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   ├── dashboard/
│   │   ├── disruptions/
│   │   └── recovery/
│   │
│   ├── components/
│   │   ├── dashboard/
│   │   ├── appointments/
│   │   ├── disruptions/
│   │   ├── recovery/
│   │   ├── calls/
│   │   └── ui/
│   │
│   ├── hooks/
│   ├── lib/
│   │   ├── api.ts
│   │   ├── utils.ts
│   │   └── constants.ts
│   │
│   ├── types/
│   └── public/
│
└── api/
    ├── app/
    │   ├── main.py
    │
    │   ├── api/                            [OWNER: Randa, except selected routes below]
    │   │   └── routes/
    │   │       ├── health.py
    │   │       ├── appointments.py
    │   │       ├── disruptions.py           [Kevin may edit]
    │   │       ├── recovery.py              [Kevin may edit]
    │   │       ├── execution.py             [Kevin may edit]
    │   │       ├── memory.py
    │   │       └── metrics.py
    │   │
    │   ├── agents/                         [OWNER: Kevin]
    │   │   ├── gemini/
    │   │   │   ├── client.py
    │   │   │   ├── researcher.py
    │   │   │   └── prompts.py
    │   │   │
    │   │   ├── nemotron/
    │   │   │   ├── client.py
    │   │   │   ├── planner.py
    │   │   │   ├── policy_engine.py
    │   │   │   └── prompts.py
    │   │   │
    │   │   └── recovery_engine.py
    │   │
    │   ├── services/                       [OWNER: Randa]
    │   │   ├── appointment_service.py
    │   │   ├── customer_service.py
    │   │   ├── disruption_service.py
    │   │   ├── calendar_service.py
    │   │   ├── notification_service.py
    │   │   ├── voice_service.py
    │   │   └── metrics_service.py
    │   │
    │   ├── tools/                          [OWNER: Kevin]
    │   │   ├── calendar_tools.py
    │   │   ├── customer_tools.py
    │   │   ├── policy_tools.py
    │   │   ├── notification_tools.py
    │   │   └── voice_tools.py
    │   │
    │   ├── schemas/                        [OWNER: Randa]
    │   │   ├── appointment.py
    │   │   ├── customer.py
    │   │   ├── disruption.py
    │   │   ├── recovery.py
    │   │   ├── execution.py
    │   │   └── memory.py
    │   │
    │   ├── db/                             [OWNER: Randa]
    │   │   ├── models/
    │   │   ├── session.py
    │   │   ├── seed.py
    │   │   └── repositories/
    │   │
    │   ├── validators/                     [OWNER: Kevin]
    │   │   ├── policy_validator.py
    │   │   ├── action_validator.py
    │   │   └── confidence_validator.py
    │   │
    │   ├── memory/                         [OWNER: Kevin]
    │   │   ├── memory_service.py
    │   │   └── preference_store.py
    │   │
    │   ├── core/                           [OWNER: Randa]
    │   │   ├── config.py
    │   │   ├── logging.py
    │   │   └── constants.py
    │   │
    │   └── utils/
    │
    └── tests/
        ├── agents/
        ├── services/
        ├── routes/
        └── fixtures/

packages/
└── contracts/                              [OWNER: Randa]
    ├── api-contract.md
    ├── frontend-types.md
    └── event-contracts.md

docs/
├── architecture.md                         [OWNER: Kevin]
├── demo-flow.md
├── api.md
├── benchmark.md                            [OWNER: Kevin]
└── decisions.md                            [shared log — anyone appends]

scripts/
├── seed_demo_data.py                       [OWNER: Randa]
├── run_benchmark.py                        [OWNER: Kevin]
└── simulate_disruption.py                  [OWNER: Randa]
```

---

## Directory-by-directory notes

### `apps/web/**` — Owner: Zaid
- **Belongs here:** all Next.js pages, React components, hooks, frontend types, client-side API wrapper.
- **Who should not edit casually:** Kevin and Randa. If AI or backend output shape changes, they must update `packages/contracts/**` and notify Zaid rather than editing frontend code directly.
- **Why separated:** frontend iteration speed (styling, layout, UX polish) is high-frequency and shouldn't be blocked by or interfere with backend/AI work.
- **Depends on:** `packages/contracts/**` (types/shape), `apps/api` REST endpoints (runtime).
- **Stable contract surface:** `apps/web/types/**` should mirror `packages/contracts/frontend-types.md` — do not diverge without updating both.

### `apps/api/app/agents/**` — Owner: Kevin
- **Belongs here:** Gemini client (world-understanding), Nemotron client (recovery planning), prompt templates, the `recovery_engine.py` orchestrator that wires the two together with tools/validators/memory.
- **Who should not edit casually:** Randa and Zaid. This is the AI reasoning core; changes here affect plan output shape, which is a contract other layers depend on.
- **Why separated:** isolates LLM/prompt logic from deterministic backend logic — keeps hallucination risk contained and makes the reasoning layer swappable/testable independently.
- **Depends on:** `apps/api/app/tools/**` (grounding facts), `apps/api/app/schemas/**` (I/O contracts), `apps/api/app/memory/**` (historical context).

### `apps/api/app/tools/**` — Owner: Kevin
- **Belongs here:** deterministic "function-call" style tools the LLM invokes (slot lookup, customer history, policy fetch, etc.) — thin wrappers that call into `services/`.
- **Who should not edit casually:** Randa (owns the services underneath) should coordinate before changing service signatures these tools call.
- **Why separated:** the model must never invent operational facts; every fact must be traceable to a deterministic tool call into real service/data layers.
- **Depends on:** `apps/api/app/services/**`.

### `apps/api/app/validators/**` — Owner: Kevin
- **Belongs here:** policy validation, confidence-threshold validation, action validation — the gate between a generated `RecoveryPlan` and execution.
- **Why separated:** keeps "is this action allowed" logic auditable and separate from both plan generation and plan execution.
- **Depends on:** `apps/api/app/schemas/recovery.py`, `apps/api/app/services/**` (for policy data).

### `apps/api/app/memory/**` — Owner: Kevin
- **Belongs here:** customer preference storage/retrieval, contact-history-aware context building for Nemotron.
- **Depends on:** `apps/api/app/db/repositories/**` (persistence), `apps/api/app/schemas/memory.py`.

### `apps/api/app/services/**` — Owner: Randa
- **Belongs here:** all backend business logic with **no LLM reasoning** — appointment/customer/calendar/notification/voice/metrics services. These are what tools and routes call.
- **Who should not edit casually:** Kevin should not add LLM calls or prompt logic here — that belongs in `agents/`.
- **Why separated:** keeps a clean, testable, mockable boundary the AI layer and frontend both depend on without either needing to know how it's implemented.
- **Depends on:** `apps/api/app/db/**`, `apps/api/app/schemas/**`.

### `apps/api/app/schemas/**` — Owner: Randa — **STABLE CONTRACT**
- **Belongs here:** every shared Pydantic model (Appointment, Customer, Disruption, RecoveryPlan, RecoveryAction, ExecutionResult, etc.).
- **Who should not edit casually:** Kevin and Zaid must not change field names/types after the first integration checkpoint without coordinating with Randa — this is the shape every layer (AI, services, frontend types) is built against.
- **Why separated:** a single source of truth for data shape prevents drift between backend, AI output, and frontend rendering.

### `apps/api/app/db/**` — Owner: Randa
- **Belongs here:** SQLAlchemy models, session management, seed logic, repositories (data access layer).
- **Who should not edit casually:** Kevin/Zaid — go through repositories/services, never query the DB directly from agents or routes.
- **Why separated:** isolates persistence details so SQLite can later be swapped without touching business logic or AI code.

### `apps/api/app/core/**` — Owner: Randa
- **Belongs here:** app configuration, logging setup, shared constants.
- **Why separated:** avoids scattering environment/config reads throughout the codebase.

### `apps/api/app/api/routes/**` — Owner: Randa, with Kevin allowed on `disruptions.py`, `recovery.py`, `execution.py`
- **Why split this way:** those three routes are the entry points into Kevin's AI pipeline, so he needs to wire them directly; all other routes are plain CRUD/service pass-throughs Randa owns.
- **Rule:** Kevin should only adjust the body of those three route handlers to call into his agents/validators — not change the shared route/response schema without coordinating with Randa.

### `packages/contracts/**` — Owner: Randa — **STABLE CONTRACT**
- **Belongs here:** `api-contract.md` (REST endpoint shapes), `frontend-types.md` (TS types mirroring Pydantic schemas), `event-contracts.md` (structured event/plan JSON shapes referenced by Gemini/Nemotron output).
- **Why separated:** a neutral, framework-agnostic contract location both frontend and backend can reference without importing each other's code.
- **Rule:** must remain stable after the first integration checkpoint (Checkpoint 2). Any change requires all three developers to agree and must be logged in `docs/decisions.md`.

### `docs/**`
- `architecture.md`, `benchmark.md` — Owner: Kevin.
- `demo-flow.md`, `api.md` — shared/Randa-maintained.
- `decisions.md` — shared log. **Anyone who makes a cross-cutting change must log it here.**

### `scripts/**`
- `run_benchmark.py` — Owner: Kevin (RecoveryBench runner).
- `seed_demo_data.py`, `simulate_disruption.py` — Owner: Randa (demo data + disruption injection for testing/demo).

### `tests/` (repo root)
- Cross-cutting/integration tests that span frontend+backend or multiple services. Component/unit tests live next to their owning code (`apps/api/tests/**`, frontend co-located tests).

---

## Dependency direction (high level)

```text
apps/web  ──consumes──>  packages/contracts  <──defines from──  apps/api/app/schemas
apps/web  ──calls REST──> apps/api/app/api/routes

apps/api/app/api/routes ──calls──> apps/api/app/services   (Randa's domain logic)
apps/api/app/api/routes ──calls──> apps/api/app/agents      (Kevin's AI orchestration, on the 3 AI routes)

apps/api/app/agents ──calls──> apps/api/app/tools ──calls──> apps/api/app/services
apps/api/app/agents ──calls──> apps/api/app/validators
apps/api/app/agents ──calls──> apps/api/app/memory ──calls──> apps/api/app/db/repositories

apps/api/app/services ──calls──> apps/api/app/db
```

Rule of thumb: **schemas and contracts are upstream of everything** and change last/rarely. Agents/tools/validators are downstream consumers of services, never the reverse.

---

## Ownership Rules

### Kevin owns

```text
repo bootstrap / initial architecture
root project structure
apps/api/app/agents/**
apps/api/app/tools/**
apps/api/app/validators/**
apps/api/app/memory/**
scripts/run_benchmark.py
docs/benchmark.md
docs/architecture.md
```

Kevin is also allowed to modify:

```text
apps/api/app/api/routes/disruptions.py
apps/api/app/api/routes/recovery.py
apps/api/app/api/routes/execution.py
```

Kevin should avoid changing shared Pydantic schemas after they are agreed upon unless coordinated.

### Randa owns

```text
apps/api/app/services/**
apps/api/app/schemas/**
apps/api/app/db/**
apps/api/app/core/**
packages/contracts/**
scripts/seed_demo_data.py
scripts/simulate_disruption.py
```

Randa should focus on backend services, database/data models, shared contracts, and stable integration plumbing.

### Zaid owns

```text
apps/web/**
```

Zaid should focus on frontend implementation and should not modify backend code unless coordinated.

**Developers should not modify files owned by another person without communicating first.**

**Shared API contracts must remain stable after the first integration checkpoint.**

---

## Suggested Git branches

```text
main
dev
feature/kevin-ai
feature/randa-backend
feature/zaid-frontend
```
