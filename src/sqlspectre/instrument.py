"""SQLAlchemy + ASGI hooks → Recorder (keep this thin)."""

from __future__ import annotations

import contextvars
import time
import uuid
from typing import Any, Callable

from sqlalchemy import event

from sqlspectre.recorder import Recorder

_fp: contextvars.ContextVar[str | None] = contextvars.ContextVar("sqlspectre_fp", default=None)


def instrument_engine(engine: Any, recorder: Recorder) -> None:
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        try:
            conn.info["sqlspectre_t0"] = time.perf_counter()
        except Exception:
            pass

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        try:
            fp = _fp.get()
            if not fp:
                return

            t0 = conn.info.pop("sqlspectre_t0", None)
            recorder.emit_query(
                {
                    "fingerprint": fp,
                    "ts": time.time(),
                    "duration_ms": round((time.perf_counter() - t0) * 1000, 3) if t0 else None,
                    "sql": sqlparse.format(statement, reindent=True),
                    "rows": cursor.rowcount,
                }
            )
        except Exception:
            pass

    def pool_event(kind: str):
        def _handler(*_args): 
            try:
                fp = _fp.get()
                if not fp:
                    return
                pool = engine.pool
                recorder.emit_engine(
                    {
                        "fingerprint": fp,
                        "ts": time.time(),
                        "event": kind,
                        "checked_out": pool.checkedout(),
                        "checked_in": pool.checkedin(),
                        "size": pool.size(),
                        "overflow": pool.overflow(),
                    }
                )
            except Exception:
                pass

        return _handler

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine.pool, "checkout", pool_event("checkout"))
    event.listen(engine.pool, "checkin", pool_event("checkin"))


class Middleware:
    def __init__(self, app: Callable, recorder: Recorder | None = None) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http" or self.recorder is None:
            await self.app(scope, receive, send)
            return

        fp = uuid.uuid4().hex[:12]
        token = _fp.set(fp)
        t0 = time.perf_counter()
        status = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                q = scope.get("query_string") or b""
                self.recorder.emit_route(
                    {
                        "fingerprint": fp,
                        "ts": time.time(),
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "query": q.decode() if isinstance(q, bytes) else q,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - t0) * 1000, 3),
                    }
                )
            except Exception:
                pass
            _fp.reset(token)
