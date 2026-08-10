# sqlspectre

Record SQLAlchemy + ASGI request activity to disk (routes, queries, pool).

**Requires:** Python ≥ 3.10, SQLAlchemy ≥ 2.0, an ASGI app with `add_middleware` (FastAPI / Starlette).

## Install from GitHub

Push this repo (the folder that contains `pyproject.toml`) to GitHub, then:

```bash
pip install git+https://github.com/<you>/<repo>.git
```

Specific branch/tag:

```bash
pip install git+https://github.com/<you>/<repo>.git@main
```

Editable local install (while developing):

```bash
pip install -e .
```

## Usage

```python
import os
import sqlspectre
from fastapi import FastAPI
from sqlalchemy import create_engine

engine = create_engine(DATABASE_URL)
app = FastAPI()

sqlspectre.attach(
    app,
    engine,
    output="./spectate",
    enabled=os.getenv("SPECTRE") == "1",
)
```

With `SPECTRE=1`, after traffic (and up to ~10s for flush) you’ll see:

```
spectate/
  routes.ndjson    # method, path, query, status, duration_ms
  queries.ndjson   # sql, duration_ms, rows
  engine.ndjson    # checkout/checkin + pool counters
```

Join lines across files with `fingerprint`.

## Layout

```
pyproject.toml
src/sqlspectre/
  __init__.py      # attach()
  instrument.py    # middleware + engine listeners
  recorder.py      # in-memory buffer → disk every 10s
docs/Overview.md
```
