# SQL Alchemy Specter

> ⚠️ **Very early / WIP.** Barely past prototype. Things are subject to change, names will change. 

sql-alchemy-specter is a profiling and load-simulation toolkit for the SQLAlchemy API development lifecycle in large, multi-thousand-user monolithic applications.

SQLAlchemy's ORM is designed to be simple in its nature, a Python API that lets you work with objects instead of SQL. 

**But** that simplicity hides a multi-layer stack (sessions, query compilation, connection pooling, hydration, serialization, ++) and the cleaner the API looks, the **harder** it gets to spot the real bottleneck at scale.

## The problem

A FastAPI + SQLAlchemy service under real traffic isn't one bottleneck — it's a stack of dependent ones:

- **Request shape** — which endpoints, with which params, in which order
- **App time** — Python / serialization / business logic between DB calls
- **Pool health** — checkout waits, saturation, overflow
- **Query cost** — what SQL actually ran, how long, how often
- **Interaction effects** — the same endpoint that looks fine alone falls apart when 200 other requests are fighting for connections

>Alchemy Specter captures the linked request chain so you can reproduce production-like load, attribute latency across the full multi-layer path where non-trivial bottlenecks emerge, and close the development loop — change, benchmark, validate against a baseline, and ship with confidence.

## How it works

One line of `attach`. While traffic runs, Spectre buffers events off the hot path and flushes flat NDJSON files under `./spectate`.

```python
engine = create_engine(DATABASE_URL)
app = FastAPI()
spectre = sqlspectre.attach(app, engine, output="./spectate", enabled=os.getenv("SPECTRE") == "1")
```

## Key features

| Feature | What it does | Why it matters |
|---|---|---|
| **One-line attach** | Wraps your ASGI app + SQLAlchemy engine in a single call | No code changes beyond one line; drop in and out freely |
| **Cross-layer instrumentation & recording** | Watches each API request and emits segmented, layer-based records (route → query → pool) in a relational pattern | Clear joins across layers; trace one request end to end or aggregate across thousands |
| **Recording, playback & historical simulation** *(historical sim soon)* | Replay production loads, tweak values to stress-test, or generate your own recordings and run dev performance tests — stored as `runs` for continuous benchmarking | Validate a change against a baseline before it ships |
| **Near-zero overhead** | Events buffer off the hot path and flush to disk in batches; fail-open and zero-cost when disabled | Recording doesn't distort the timings it measures, and never breaks a request |
| **Production-faithful playback** | Auto-spins pool / thread / connection concurrency during replay to mirror the real server | Reproduces genuine contention (pool starvation, queueing), not a model of it |
| **Visualization & HTML reports** | Per-endpoint evaluation with run-time percentiles, longest requests, query breakdowns, and more | See which endpoints degrade and *why*, in one self-contained file |
| **Multi-engine** | `engine_id` stamped on every event | Read/write splits, replicas, and analytics pools stay separable |
| **Flat NDJSON facts** | Fixed-column files linked by id | Clean joins and direct ETL / OLAP loads, no nested parsing |
## What the recordings give you


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

| File | Grain | What's in it |
|---|---|---|
| `recording` | request | method, path, status, hashed user/session, ts — the lean tape for replay |
| `request_params` | param | query / path / body keys as normalized rows (replay inputs, ETL-friendly) |
| `routes` | request | total vs process vs db vs response timing — where time actually went |
| `queries` | query | `sql`, `sql_shape`, ms, rows — joined back via `request_id` + `query_id` |
| `pool_lifecycle` | pool event | checkout → query(+) → checkin stages, with time per stage |
| `pool_summary` | request × engine | cumulative pool rollup |

Pool lifecycle is the fun one for contention: you can literally see time sitting in checkout/hold vs execute when the pool starts starving.

