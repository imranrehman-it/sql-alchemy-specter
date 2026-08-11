# August 2026

```text
august/
├── [2026-08-10](#2026-08-10) — init, multi-engine, flat log structure, example API
└── [2026-08-11](#2026-08-11) — rows.py, response instruments, config, recording lifecycle
```

---

# 2026-08-10

## Init + Multi Engine

- Scaffolded `sqlspectre` package (attach → instrument → recorder)
- Wired up `test-api` as a FastAPI + SQLAlchemy harness
- Request logging working: routes, queries, and pool events → NDJSON
- Replaced per-row disk writes with an in-memory buffer + batch flush to cut I/O overhead
- Multi-engine monitoring with `engine_id` on query/pool events (`feat/statistic` → merged)
- Fail-open hot path: recorder errors never break requests
- Correlated HTTP + SQL activity via per-request `fingerprint`

## Record + structure

- Switched to flat NDJSON schemas with fixed columns (no nested lists/objects)

  - reason: easier ETL / warehouse loads and joins

- Introduced linking ids: `request_id`, `query_id`, `event_id`

  - reason: avoid duplicating facts across files

- Added `recording.ndjson` (method, path, user/session, status, ts)

  - reason: lean traffic tape for replay

- Added `request_params.ndjson` (source/key/value rows)

  - reason: keep params normalized instead of nested blobs

- Expanded route timing: process / db / response breakdown

  - reason: see where request time goes

- Split pool logging into `pool_lifecycle` + `pool_summary`

  - reason: stage timeline vs cumulative totals

- Generate `query_id` per statement; lifecycle query stages link to `queries`

  - reason: reconstruct checkout → query → checkin order

- Short engine ids (`postgresql/spectre`), hashed sessions, compact SQL + `sql_shape`

  - reason: cut log size and avoid leaking secrets

- Reorganized package into attach / middleware / engine / recorder / extract / util

  - reason: smaller modules, same public `attach()` API

```text
spectate/
┌──────────────────┐
│ recording        │  1 row / request
│ request_id (PK)  │  method, path, status, user, session, ts
└────────┬─────────┘
         │ request_id
    ┌────┴────┬──────────────┬────────────────┐
    ▼         ▼              ▼                ▼
┌────────┐ ┌────────┐ ┌────────────┐ ┌────────────────┐
│request_│ │ routes │ │  queries   │ │ pool_lifecycle │
│params  │ │        │ │            │ │                │
│        │ │timing  │ │query_id PK │ │event_id PK     │
│1 row / │ │only    │ │sql, ms,    │ │checkout→query  │
│param   │ │        │ │sql_shape   │ │→checkin        │
└────────┘ └────────┘ └─────┬──────┘ └───────┬────────┘
                            │ query_id       │
                            └────────┬───────┘
                                     ▼
                            ┌────────────────┐
                            │ pool_summary   │
                            │ 1 row /        │
                            │ request×engine │
                            └────────────────┘

Join keys
  request_id  → ties all files to one HTTP request
  query_id    → ties queries ↔ pool_lifecycle (query stages)
  event_id    → unique pool_lifecycle row
  engine      → which DB engine (multi-engine safe)
```

```text
recording (request_id)
    ├── request_params     (request_id)          # replay inputs
    ├── routes             (request_id)          # process/db/response timing
    ├── queries            (request_id, query_id)
    ├── pool_lifecycle     (request_id, query_id on query stages)
    └── pool_summary       (request_id, engine)  # cumulative rollup
```

## Added example API + readme.

---

# 2026-08-11

## Central log shapes (`rows.py`)

- Moved all log row formatting into one place
- Each file (recording, queries, routes, etc.) has a single builder instead of dicts scattered across middleware/engine
- Makes it way easier to keep columns consistent when we add or tweak fields

## Response instruments

- Started measuring how long the response side actually takes
- Tracks:
  - `build_ms` — building the payload
  - `encode_ms` — JSON encoding
  - `send_ms` — shipping it over ASGI
  - `response_bytes` — body size
- New files: `response_size` + `response_timing`
- Also added pool wait timing so we can spot checkout bottlenecks
- Heads up: JSON responses only for now — streams can log a bit early on the first chunk

## Config (csv / ndjson for now)

- Added `configure()` + `Settings` so you can pick:
  - output dir
  - `csv` or `ndjson`
  - enabled on/off
  - flush interval + max buffer
- File logs are temporary — next up is swapping this for queue-based inserts into a DB
- Example API already uses `configure(...)` before `attach()`

## Recording lifecycle

- Recordings are real sessions now, not just a boolean
- Core calls on the handle / recorder:
  - `start()` — new recording (or resume if paused); errors if already running
  - `pause()` — stop collecting, keep the same recording id
  - `stop()` — end it, stamp `ended_at`, return the details
  - `details()` — peek at current / last recording
- Each recording gets an `id` + `started_at`
- After stop, the next `start()` kicks off a fresh recording
- Output goes into a per-session folder: `{id}_{YYYY-MM-DD}/` with a `meta.json`

```text
start → running → pause → (start resumes) → stop → start again = new id
```

## Example API

- Wired up endpoints for the above: `/start-recording`, `/pause-recording`, `/stop-recording`, `/recording`
- Start returns 409 if a recording is already going
