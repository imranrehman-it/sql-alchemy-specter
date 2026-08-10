## Small helpers for ids, SQL shaping, and safe pool counters.

from __future__ import annotations

import hashlib
import re
import time
import uuid
from typing import Any

_SQL_MAX = 240
_WS = re.compile(r"\s+")

POOL_ATTRS = (
    ("pool_out", "checkedout"),
    ("pool_idle", "checkedin"),
    ("pool_size", "size"),
    ("pool_overflow", "overflow"),
)


def new_id(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def resolve_engine_id(engine: Any, engine_id: str | None = None) -> str:
    if engine_id:
        return engine_id
    try:
        url = engine.url
        return f"{url.get_backend_name()}/{url.database or 'db'}"
    except Exception:
        return f"engine-{id(engine):x}"


def sql_compact(sql: str) -> str:
    s = _WS.sub(" ", sql).strip()
    return s if len(s) <= _SQL_MAX else s[: _SQL_MAX - 1] + "…"


def sql_shape(sql: str) -> str:
    return hashlib.sha1(_WS.sub(" ", sql).strip().lower().encode()).hexdigest()[:12]


def pool_cols(pool: Any) -> dict[str, Any]:
    cols = {col: None for col, _ in POOL_ATTRS}
    for col, attr in POOL_ATTRS:
        try:
            val = getattr(pool, attr)
            cols[col] = val() if callable(val) else val
        except Exception:
            pass
    return cols


def lifecycle_row(
    *,
    request_id: str,
    engine: str,
    event: str,
    t_ms: float | None,
    time_spent: float | None = None,
    query_id: str | None = None,
    pool: dict[str, Any] | None = None,
    ts: float | None = None,
) -> dict[str, Any]:
    row = {
        "event_id": new_id(10),
        "request_id": request_id,
        "query_id": query_id,
        "engine": engine,
        "event": event,
        "ts": round(ts if ts is not None else time.time(), 3),
        "t_ms": t_ms,
        "time_spent": time_spent,
        "pool_out": None,
        "pool_idle": None,
        "pool_size": None,
        "pool_overflow": None,
    }
    if pool:
        row.update(pool)
    return row
