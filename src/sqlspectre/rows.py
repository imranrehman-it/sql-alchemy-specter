## One builder per spectate NDJSON file. Shapes live only here.

from __future__ import annotations

from typing import Any


def recording(
    *,
    request_id: str,
    ts: float,
    method: str | None,
    path: str,
    status: int,
    user_id: str | None,
    session: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "ts": ts,
        "method": method,
        "path": path,
        "status": status,
        "user_id": user_id,
        "session": session,
    }


def request_params(
    *,
    request_id: str,
    source: str,
    key: str,
    value: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "source": source,
        "key": key,
        "value": value,
    }


def routes(
    *,
    request_id: str,
    ts: float,
    total_ms: float,
    process_ms: float,
    db_ms: float,
    response_ms: float,
    query_count: int,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "ts": ts,
        "total_ms": total_ms,
        "process_ms": process_ms,
        "db_ms": db_ms,
        "response_ms": response_ms,
        "query_count": query_count,
    }


def queries(
    *,
    query_id: str,
    request_id: str,
    engine: str,
    ts: float,
    t_ms: float | None,
    ms: float | None,
    sql_shape: str,
    sql: str,
    rows: int | None,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "request_id": request_id,
        "engine": engine,
        "ts": ts,
        "t_ms": t_ms,
        "ms": ms,
        "sql_shape": sql_shape,
        "sql": sql,
        "rows": rows,
    }


def pool_lifecycle(
    *,
    event_id: str,
    request_id: str,
    engine: str,
    event: str,
    ts: float,
    t_ms: float | None,
    query_id: str | None = None,
    time_spent: float | None = None,
    pool_out: int | None = None,
    pool_idle: int | None = None,
    pool_size: int | None = None,
    pool_overflow: int | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "request_id": request_id,
        "engine": engine,
        "event": event,
        "ts": ts,
        "t_ms": t_ms,
        "query_id": query_id,
        "time_spent": time_spent,
        "pool_out": pool_out,
        "pool_idle": pool_idle,
        "pool_size": pool_size,
        "pool_overflow": pool_overflow,
    }


def pool_summary(
    *,
    request_id: str,
    engine: str,
    ts: float,
    checkouts: int,
    queries: int,
    query_ms: float,
    wait_ms: float,
    hold_ms: float,
    total_ms: float,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "engine": engine,
        "ts": ts,
        "checkouts": checkouts,
        "queries": queries,
        "query_ms": query_ms,
        "wait_ms": wait_ms,
        "hold_ms": hold_ms,
        "total_ms": total_ms,
    }
