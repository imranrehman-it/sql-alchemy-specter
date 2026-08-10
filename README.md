## SQL Alchemy Specter

> ⚠️ **Very early / WIP.** Barely past prototype. Things are half-built, names will change, and the recording format is not stable. Don't depend on this yet. If you do, pin to a commit.

`sqlspectre` records what your SQLAlchemy + ASGI app actually does per request: routes, queries, and connection-pool activity, writing it to disk for later analysis.

The goal (mostly not built yet) is to benchmark production-scale request load by replaying realistic traffic against staging, so you can see how an implementation holds up under production-like contention and catch issues before they hit prod.

Right now it does the recording part. The replay/report side is still being figured out.

## What it captures (so far)

Chains every layer of a request together with a unique per-request `fingerprint`:

```
request  ──fingerprint──┐
                        │
├─ Request details      │  method, path, status, total duration
│                       │  hashed into the fingerprint that links everything below
│                       │
├─ Engine pool          │  checkout/checkin events, active connections,
│    contention/health  │  pool size, overflow → saturation & starvation
│                       │
├─ Database             │  each query's SQL, timing, row counts,
│    transactions       │  tied back to the issuing request
│                       │
├─ API request/response │  time in application code vs. database,
│    processing         │  showing where each request spends its time
│                       │
└─ Summary timeseries   │  activity aggregated over time: how load,
                        ┘  latency, and contention evolve across a session
```

Everything joins on `fingerprint`, so a request can be traced end to end from the HTTP call down to the queries and pool events it triggered.

## Status

- [x] Per-request recording (routes, queries, pool) to disk
- [x] Cross-layer `fingerprint` correlation
- [ ] Load replay against staging
- [ ] HTML report / analysis
- [ ] Write-traffic handling
- [ ] Stable recording format

**Dependencies**
- Python ≥ 3.10
- SQLAlchemy ≥ 2.0
- An ASGI app with `add_middleware` (FastAPI / Starlette)

**Install**
```bash
pip install git+https://github.com/imranrehman-it/sql-alchemy-specter
```

For local development:
```bash
pip install -e .
```

Add one line where you build your engine and app:
```python
import os
import sqlspectre
from sqlalchemy import create_engine
from fastapi import FastAPI

engine = create_engine(DATABASE_URL)
app = FastAPI()

# The only line you add:
spectre = sqlspectre.attach(app, engine, output="./spectate", enabled=os.getenv("SPECTRE") == "1")
```

Adjust the checkboxes in **Status** to match what's actually working — I guessed at the split based on our earlier conversation.
