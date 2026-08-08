# NEXUS Platform — Architecture

This document defines the MVP scope, component design, and build order for the NEXUS Engineering Challenge implementation. It follows the handbook (NX-CH-001 v1.0) requirement priority.

## Handbook analysis summary

### The five platform promises (Part One)

| Promise | MVP mapping |
|---------|-------------|
| Work is never lost | R-01 persistence + R-02 terminal states |
| Releases can be undone | R-06 simplified release/rollback |
| Disagreements are noticed | R-08 (stretch — stock cache demo) |
| Failure has a floor | R-04 retry/restart limits |
| The past can be reconstructed | R-05 event history + operator dashboard |

### Requirement priority (Part Two §2.3)

**Must implement convincingly (CORE):**

| Ref | Requirement | Implementation |
|-----|-------------|----------------|
| R-01 | Accepted work is safe | SQLite commit before ACK; WAL mode |
| R-02 | Every piece of work ends somewhere | States: COMPLETED or FAILED only; no silent drop |
| R-03 | Doing it twice is harmless | Client work ID + idempotent completion ledger |
| R-04 | Trying again has a limit | Max work retries + worker restart budget |
| R-05 | You can ask about the past | Append-only `events` table + query API |
| R-06 | Changes can be undone | Release registry + one-action rollback |

**Target if core is solid (EXPECTED):**

| Ref | Requirement | Implementation |
|-----|-------------|----------------|
| R-07 | Changes linked to effects | Release events on shared timeline |
| R-12 | 90-second operator clarity | Dashboard health summary with plain-language diagnosis |
| R-15 | Failures can be triggered | Simulation API + dashboard controls |

**Explicitly deferred (honest in ACCOUNT.md):**

- R-08–R-11: Full cache disagreement, dependency degradation, backlog rate limiting
- R-13–R-14: Order guarantees, self-query API
- Multi-service mesh (40 services) — we model 1 producer + 1–2 workers

### Build order (handbook §3.1)

```
R-01 (persist) → R-02 (terminal states) → R-05 (events)
                      ↓
              R-03 (idempotency) + R-04 (limits)
                      ↓
              R-06 (rollback) + operator dashboard + simulation
```

---

## MVP scope (~6 hours)

### In scope

1. **Platform** — FastAPI app: accept work, dispatch, retry, dead-letter, worker health
2. **Stand-ins** — HTTP producer CLI + 1–2 poll-based worker processes
3. **Operator dashboard** — Single HTML page with health diagnosis, not raw metrics
4. **Failure simulation** — Kill worker, crash loop, slow worker, duplicate delivery, platform restart
5. **Tests** — Persistence, retry limit, idempotency, worker budget exhaustion
6. **Docs** — README.md (run/break/use) + ACCOUNT.md (six handbook sections)

### Out of scope (documented, not hidden)

- Distributed multi-machine deployment
- Full cache/stock disagreement system (optional demo if time)
- Backlog drain rate limiting (R-11)
- Load-based release validation

---

## System architecture

```
┌─────────────┐     POST /work          ┌──────────────────────────────────────┐
│  Producer   │ ───────────────────────►│           NEXUS Platform             │
│  (CLI/API)  │                         │  ┌────────────┐  ┌───────────────┐ │
└─────────────┘                         │  │ WorkService│  │ EventService  │ │
                                        │  └─────┬──────┘  └───────▲───────┘ │
┌─────────────┐     poll + complete     │        │                 │         │
│  Worker(s)  │ ◄──────────────────────►│  ┌─────▼──────┐  ┌───────┴───────┐ │
│  (process)  │                         │  │ Dispatcher │  │ WorkerManager│ │
└─────────────┘                         │  │   Loop     │  │  + Recovery  │ │
                                        │  └─────┬──────┘  └───────────────┘ │
┌─────────────┐     GET /dashboard      │        │                            │
│  Operator   │ ◄──────────────────────►│  ┌─────▼──────┐  ┌───────────────┐ │
│  (browser)  │                         │  │   SQLite   │  │  Simulation   │ │
└─────────────┘                         │  │   (local)  │  │     API       │ │
                                        │  └────────────┘  └───────────────┘ │
                                        └──────────────────────────────────────┘
```

### Process model

| Process | Role |
|---------|------|
| `python -m nexus.run` | Starts uvicorn + background loops + optional embedded workers |
| `python -m worker.run --id worker-1` | Stand-in worker (separate process for kill/crash demos) |
| `python -m producer.submit` | Submits sample work |

One-command startup script (`start.ps1` / `start.sh`) launches platform + workers together.

---

## Data model

### Work item (`works`)

| Field | Purpose |
|-------|---------|
| `id` | Client-provided idempotency key (TEXT PK) |
| `type` | Work type string |
| `body` | JSON payload |
| `status` | ACCEPTED \| PROCESSING \| RETRY_WAIT \| COMPLETED \| FAILED |
| `attempt_count` | Delivery attempts so far |
| `max_attempts` | Default 5 |
| `created_at`, `updated_at`, `accepted_at` | Timestamps (UTC ISO) |
| `next_retry_at` | When RETRY_WAIT becomes eligible |
| `assigned_worker_id` | Current lease holder |
| `lease_expires_at` | Detect worker death mid-processing |
| `last_error` | Most recent failure reason |
| `completed_at` | Set on COMPLETED or FAILED |

### Completion ledger (`completions`)

Ensures R-03: duplicate `complete` calls return the same result without double side effects.

| Field | Purpose |
|-------|---------|
| `work_id` | PK, FK to works |
| `result` | JSON result body |
| `completed_at` | First completion time |
| `completion_count` | Times complete was called (visibility) |

### Worker registry (`workers`)

| Field | Purpose |
|-------|---------|
| `id` | Worker identifier |
| `status` | RUNNING \| RESTARTING \| OUT_OF_SERVICE \| SLOW |
| `restart_count` | Restarts in current window |
| `max_restarts` | Default 5 |
| `last_heartbeat_at` | Liveness |
| `next_restart_at` | Backoff before next restart |
| `failure_mode` | normal \| crash \| slow \| killed |
| `release_version` | Current deployed version (R-06/R-07) |

### Events (`events`) — R-05

Append-only audit log:

| Field | Purpose |
|-------|---------|
| `id` | Auto-increment |
| `timestamp` | UTC |
| `event_type` | work \| worker \| release \| operator \| system |
| `subject_type` | work \| worker \| release \| platform |
| `subject_id` | Entity id |
| `action` | accepted, dispatched, failed, retry_scheduled, completed, dead_letter, restarted, out_of_service, released, rolled_back, … |
| `reason` | Human-readable explanation |
| `details` | JSON context (attempt #, worker id, release version, etc.) |

### Releases (`releases`) — R-06/R-07

| Field | Purpose |
|-------|---------|
| `id` | Release id |
| `component` | worker name |
| `version` | New version string |
| `previous_version` | For rollback |
| `status` | deploying \| active \| rolled_back \| failed |
| `deployed_at`, `rolled_back_at` | Timestamps |

---

## Core behaviours

### R-01: Accept work safely

1. Producer sends `POST /api/work` with `{ id, type, body }`.
2. Platform inserts into SQLite inside a transaction.
3. Only after commit succeeds → return `202 Accepted` with work record.
4. Duplicate `id` → return existing work (201/200), no second row.

### R-02: Terminal states only

State machine:

```
ACCEPTED ──dispatch──► PROCESSING ──success──► COMPLETED
                           │
                           ├──fail (retries left)──► RETRY_WAIT ──backoff──► ACCEPTED
                           │
                           └──fail (no retries)──► FAILED (dead letter)
```

On platform restart: PROCESSING with expired lease → RETRY_WAIT (preserve `attempt_count`).

### R-03: Idempotent delivery

- **Accept**: same `id` → same work row.
- **Complete**: `POST /api/work/{id}/complete` writes `completions` once; repeats return stored result and emit `duplicate_completion` event.
- **Dispatch**: worker receives `delivery_id` (attempt-scoped); worker should check completion before processing (documented contract).

### R-04: Limits

**Work retries:**

- `max_attempts = 5`
- Backoff: `min(300, 2^attempt_count)` seconds (capped exponential)
- Exhausted → FAILED + event `dead_letter`

**Worker restarts:**

- `max_restarts = 5` within a 10-minute sliding window
- Restart backoff: `min(120, 2^restart_count)` seconds
- Budget exhausted → OUT_OF_SERVICE (stops receiving work)
- Manual recovery: `POST /api/workers/{id}/recover`

### R-05: Event history

Every state transition and operator/simulation action appends an event. Dashboard and `GET /api/events` expose grouped timeline.

### R-06: Rollback (simplified)

- `POST /api/releases` deploys a version to a worker component.
- Platform stores `previous_version` before deploy.
- `POST /api/releases/{id}/rollback` restores previous version in one action.
- Rollback emits linked events on the shared timeline (R-07 partial).

---

## Background loops (asyncio)

| Loop | Interval | Responsibility |
|------|----------|----------------|
| **Dispatcher** | 1s | Move ACCEPTED / due RETRY_WAIT → PROCESSING; assign to healthy workers |
| **Lease watchdog** | 2s | Expired PROCESSING leases → RETRY_WAIT |
| **Retry scheduler** | 1s | Promote RETRY_WAIT when `next_retry_at <= now` |
| **Worker recovery** | 2s | Restart crashed workers within budget; mark OUT_OF_SERVICE when exhausted |
| **Health aggregator** | 5s | Compute platform health summary for dashboard |

All loops are deterministic: use injected `clock` (default `time.time()`, overridable in tests).

---

## API surface (planned)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/work` | Submit work |
| GET | `/api/work` | List/filter work |
| GET | `/api/work/{id}` | Work detail + history |
| POST | `/api/work/{id}/claim` | Worker polls next work |
| POST | `/api/work/{id}/complete` | Idempotent completion |
| POST | `/api/work/{id}/fail` | Report processing failure |
| GET | `/api/workers` | Worker states |
| POST | `/api/workers/{id}/heartbeat` | Worker liveness |
| POST | `/api/workers/{id}/recover` | Manual recovery |
| GET | `/api/events` | Event timeline |
| GET | `/api/health/summary` | Operator diagnosis JSON |
| POST | `/api/simulate/*` | Failure injection |
| POST | `/api/releases` | Deploy version |
| POST | `/api/releases/{id}/rollback` | Undo release |
| GET | `/` | Operator dashboard |

---

## Operator dashboard (R-12)

Plain-language sections:

1. **What's wrong** — e.g. "Worker worker-1 is OUT_OF_SERVICE after 5 crash restarts"
2. **Since when** — timestamp of first symptom event
3. **What changed** — recent releases/operator actions on same timeline
4. **Work queue** — pending count, oldest pending age, failed count
5. **Components** — worker cards with status, restart count, failure mode
6. **Recent events** — scrollable timeline with reasons

Auto-refresh every 3s. No external CDN dependencies.

---

## Failure simulation (reviewer scenarios)

| Scenario | Trigger | Expected behaviour |
|----------|---------|-------------------|
| Worker killed mid-processing | `POST /api/simulate/worker/{id}/kill` | Lease expires → retry with preserved attempts |
| Platform restart with pending work | Stop/start process | Work survives; dispatcher resumes |
| Worker crash loop | `failure_mode=crash` | Restarts until budget → OUT_OF_SERVICE |
| Worker slow | `failure_mode=slow` | Heartbeat/slow flag visible; work ages in queue |
| Duplicate delivery | Re-dispatch same work or duplicate complete | Idempotent result; event logged |
| Bad release + rollback | Deploy bad version → rollback | Previous version restored in one action |

---

## Configuration (`nexus/config.py`)

| Setting | Default |
|---------|---------|
| `DATABASE_PATH` | `./data/nexus.db` |
| `HOST` | `127.0.0.1` |
| `PORT` | `8000` |
| `MAX_WORK_ATTEMPTS` | `5` |
| `MAX_WORKER_RESTARTS` | `5` |
| `LEASE_SECONDS` | `30` |
| `RESTART_WINDOW_SECONDS` | `600` |

---

## Project layout

```
nexus-deepika/
├── ARCHITECTURE.md          ← this file
├── README.md                ← run / use / break instructions
├── ACCOUNT.md               ← handbook written account
├── requirements.txt
├── start.ps1 / start.sh     ← one-command startup
├── nexus/
│   ├── main.py              ← FastAPI app factory
│   ├── run.py               ← startup entrypoint
│   ├── config.py
│   ├── database.py          ← SQLite + schema init
│   ├── models.py            ← enums + pydantic models
│   ├── schema.sql
│   ├── clock.py             ← injectable time for tests
│   ├── services/            ← business logic
│   ├── engine/              ← background loops
│   ├── api/                 ← route handlers
│   └── static/              ← operator dashboard
├── worker/
│   └── run.py               ← stand-in worker process
├── producer/
│   └── submit.py            ← stand-in producer CLI
└── tests/
    ├── conftest.py
    └── test_*.py
```

---

## Implementation phases

| Phase | Deliverable | Verify |
|-------|-------------|--------|
| 1 | DB schema + config + app skeleton | App starts, `/health` OK |
| 2 | Work accept + persist (R-01) | Test: survive restart |
| 3 | Dispatch + worker poll/complete (R-02) | Work reaches COMPLETED |
| 4 | Retry + dead letter (R-04) | Test: limit respected |
| 5 | Idempotency (R-03) | Test: duplicate safe |
| 6 | Worker recovery budget (R-04) | Test: OUT_OF_SERVICE |
| 7 | Event log (R-05) | Timeline queryable |
| 8 | Operator dashboard (R-12) | Plain-language diagnosis |
| 9 | Simulation API (R-15) | Each scenario triggerable |
| 10 | Releases + rollback (R-06) | One-action undo |
| 11 | README + ACCOUNT + start script | Fresh-machine test |

---

## Design principles

- **Persist before ACK** — never tell the producer "accepted" until SQLite commits.
- **Preserve attempt counts across restart** — R-01/R-04 depend on this.
- **Events are cheap** — synchronous insert in same transaction as state change when possible.
- **Separate worker process** — enables real kill/crash demos without mocking.
- **No network at runtime** — static assets bundled; SQLite local file only.
