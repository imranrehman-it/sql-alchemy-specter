# example-api

Local FastAPI + SQLAlchemy + Postgres harness for developing and demoing `sqlspectre`.

**What it provides**

- Small CRUD API (`users`, `merchants`, `orders`) on SQLAlchemy 2.0
- Postgres 16 via Docker Compose (port `5435`)
- `sqlspectre.attach(...)` wired in so request/query/pool activity is recorded to `./spectate/`
- Alembic migrations so the schema comes up cleanly

The API process runs on your machine (uvicorn `--reload`). Only the database is containerized.

## Setup

Commands run from `example-api/api`:

```bash
cd example-api/api

cp .env.example .env
docker compose up -d

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e ../..        # editable sqlspectre (package root)
python -m alembic upgrade head
```

Use `python -m alembic` / `python -m uvicorn` so you always hit this folder’s `.venv`, not a global or leftover install.
`.env.example` sets `DATABASE_URL` and `SPECTRE=1`.

## Run

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

```bash
curl http://localhost:8001/health
```

| | |
|---|---|
| API | http://localhost:8001 |
| Docs | http://localhost:8001/docs |
| Recordings | `./spectate/` (flush ~10s) |

## Recordings

With `SPECTRE=1`:

```text
spectate/
  recording.ndjson
  request_params.ndjson
  routes.ndjson
  queries.ndjson
  pool_lifecycle.ndjson
  pool_summary.ndjson
```

## Useful commands

```bash
python -m alembic revision --autogenerate -m "describe change"
python -m alembic upgrade head
python -m alembic current

docker compose down        # stop Postgres
docker compose down -v     # wipe DB volume
```

## Layout

```text
example-api/
  README.md
  api/
    app/                 # FastAPI app + models
    alembic/             # migrations
    docker-compose.yml   # Postgres only
    requirements.txt
    .env.example
```

Editable install means changes under `src/sqlspectre` reload with the API. `.env` and `spectate/` are gitignored.
