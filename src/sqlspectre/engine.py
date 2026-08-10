## Hook SQLAlchemy engine + pool events into the recorder.

from __future__ import annotations

import contextvars
import time
from typing import Any

from sqlalchemy import event

from sqlspectre.context import req_state_var, request_id_var
from sqlspectre.recorder import Recorder
from sqlspectre.rows import pool_lifecycle, queries
from sqlspectre.util import (
    new_id,
    pool_cols,
    resolve_engine_id,
    sql_compact,
    sql_shape,
)

# last wait from pool._do_get → consumed on checkout
_pool_wait_ms: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "sqlspectre_pool_wait_ms", default=None
)


def _patch_pool_wait(pool: Any) -> None:
    if getattr(pool, "_sqlspectre_wait_patched", False):
        return
    orig = pool._do_get

    def _do_get():
        t0 = time.perf_counter()
        try:
            return orig()
        finally:
            _pool_wait_ms.set(round((time.perf_counter() - t0) * 1000, 3))

    pool._do_get = _do_get
    pool._sqlspectre_wait_patched = True


def instrument_engine(
    engine: Any,
    recorder: Recorder,
    engine_id: str | None = None,
) -> str:
    eid = resolve_engine_id(engine, engine_id)
    _patch_pool_wait(engine.pool)

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        try:
            conn.info["sqlspectre_t0"] = time.perf_counter()
        except Exception:
            pass

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        try:
            request_id = request_id_var.get()
            if not request_id:
                return

            t0 = conn.info.pop("sqlspectre_t0", None)
            now = time.perf_counter()
            ms = round((now - t0) * 1000, 3) if t0 else None
            query_id = new_id(10)
            t_ms = None

            state = req_state_var.get()
            if state is not None and t0 is not None:
                t_ms = round((t0 - state.t0) * 1000, 3)
                if ms is not None:
                    state.db_ms += ms
                    state.for_engine(eid).query_ms += ms
                state.query_count += 1
                state.for_engine(eid).queries += 1

            rows = cursor.rowcount
            if rows is not None and rows < 0:
                rows = None

            ts = round(time.time(), 3)
            recorder.emit(
                "queries",
                queries(
                    query_id=query_id,
                    request_id=request_id,
                    engine=eid,
                    ts=ts,
                    t_ms=t_ms,
                    ms=ms,
                    sql_shape=sql_shape(statement),
                    sql=sql_compact(statement),
                    rows=rows,
                ),
            )
            recorder.emit(
                "pool_lifecycle",
                pool_lifecycle(
                    event_id=new_id(10),
                    request_id=request_id,
                    engine=eid,
                    event="query",
                    ts=ts,
                    t_ms=t_ms,
                    query_id=query_id,
                    time_spent=ms,
                ),
            )
        except Exception:
            pass

    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        try:
            request_id = request_id_var.get()
            if not request_id:
                return
            now = time.perf_counter()
            wait_ms = _pool_wait_ms.get()
            _pool_wait_ms.set(None)
            connection_record.info["sqlspectre_checkout_t0"] = now
            state = req_state_var.get()
            t_ms = None
            if state is not None:
                state.for_engine(eid).checkouts += 1
                if wait_ms is not None:
                    state.for_engine(eid).wait_ms += wait_ms
                t_ms = round((now - state.t0) * 1000, 3)
            recorder.emit(
                "pool_lifecycle",
                pool_lifecycle(
                    event_id=new_id(10),
                    request_id=request_id,
                    engine=eid,
                    event="checkout",
                    ts=round(time.time(), 3),
                    t_ms=t_ms,
                    time_spent=wait_ms,
                    **pool_cols(engine.pool),
                ),
            )
        except Exception:
            pass

    def on_checkin(dbapi_connection, connection_record):
        try:
            request_id = request_id_var.get()
            if not request_id:
                return
            now = time.perf_counter()
            t0 = connection_record.info.pop("sqlspectre_checkout_t0", None)
            hold_ms = round((now - t0) * 1000, 3) if t0 is not None else None
            state = req_state_var.get()
            t_ms = None
            if state is not None:
                if hold_ms is not None:
                    state.for_engine(eid).hold_ms += hold_ms
                t_ms = round((now - state.t0) * 1000, 3)
            recorder.emit(
                "pool_lifecycle",
                pool_lifecycle(
                    event_id=new_id(10),
                    request_id=request_id,
                    engine=eid,
                    event="checkin",
                    ts=round(time.time(), 3),
                    t_ms=t_ms,
                    time_spent=hold_ms,
                    **pool_cols(engine.pool),
                ),
            )
        except Exception:
            pass

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine.pool, "checkout", on_checkout)
    event.listen(engine.pool, "checkin", on_checkin)
    return eid
