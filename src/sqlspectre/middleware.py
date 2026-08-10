## ASGI middleware that correlates each HTTP request and writes flat event rows.

from __future__ import annotations

import time
from typing import Callable

from sqlspectre.context import ReqState, req_state_var, request_id_var
from sqlspectre.extract import (
    BODY_MAX,
    SKIP_PATHS,
    cookies,
    find_user_id,
    headers,
    iter_params,
    parse_body,
    query_params,
    session_id,
)
from sqlspectre.recorder import Recorder
from sqlspectre.rows import pool_summary, recording, request_params, routes
from sqlspectre.util import new_id


class Middleware:
    def __init__(self, app: Callable, recorder: Recorder | None = None) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http" or self.recorder is None:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path or path in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        request_id = new_id(12)
        state = ReqState(t0=time.perf_counter())
        time_call = time.time()
        rid_token = request_id_var.set(request_id)
        req_token = req_state_var.set(state)
        status = 0
        t_response_start: float | None = None
        body_buf = bytearray()
        body_truncated = False

        async def receive_wrapper() -> dict:
            nonlocal body_truncated
            message = await receive()
            try:
                if message.get("type") == "http.request" and not body_truncated:
                    chunk = message.get("body") or b""
                    if chunk:
                        room = BODY_MAX - len(body_buf)
                        if room > 0:
                            body_buf.extend(chunk[:room])
                        if len(body_buf) >= BODY_MAX or len(chunk) > room:
                            body_truncated = True
            except Exception:
                pass
            return message

        async def send_wrapper(message: dict) -> None:
            nonlocal status, t_response_start
            if message["type"] == "http.response.start":
                status = message["status"]
                t_response_start = time.perf_counter()
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            try:
                self._finish(
                    scope,
                    request_id,
                    state,
                    time_call,
                    status,
                    t_response_start,
                    bytes(body_buf),
                    path,
                )
            except Exception:
                pass
            req_state_var.reset(req_token)
            request_id_var.reset(rid_token)

    def _finish(
        self,
        scope: dict,
        request_id: str,
        state: ReqState,
        time_call: float,
        status: int,
        t_response_start: float | None,
        body_bytes: bytes,
        path: str,
    ) -> None:
        assert self.recorder is not None
        total_ms = (time.perf_counter() - state.t0) * 1000
        pre_ms = (
            (t_response_start - state.t0) * 1000
            if t_response_start is not None
            else total_ms
        )
        response_ms = max(0.0, total_ms - pre_ms)
        process_ms = max(0.0, pre_ms - state.db_ms)

        query = query_params(scope.get("query_string") or b"")
        path_params = dict(scope.get("path_params") or {})
        hdrs = headers(scope)
        cook = cookies(hdrs.get("cookie", ""))
        body = parse_body(body_bytes, hdrs.get("content-type", ""))
        ts = round(time_call, 3)
        total_ms_r = round(total_ms, 3)

        self.recorder.emit(
            "recording",
            recording(
                request_id=request_id,
                ts=ts,
                method=scope.get("method"),
                path=path,
                status=status,
                user_id=find_user_id(hdrs, cook, query, path_params),
                session=session_id(hdrs, cook),
            ),
        )
        for source, key, value in iter_params(query, path_params, body):
            self.recorder.emit(
                "request_params",
                request_params(
                    request_id=request_id,
                    source=source,
                    key=key,
                    value=value,
                ),
            )
        self.recorder.emit(
            "routes",
            routes(
                request_id=request_id,
                ts=ts,
                total_ms=total_ms_r,
                process_ms=round(process_ms, 3),
                db_ms=round(state.db_ms, 3),
                response_ms=round(response_ms, 3),
                query_count=state.query_count,
            ),
        )
        for eng, stats in state.engines.items():
            self.recorder.emit(
                "pool_summary",
                pool_summary(
                    request_id=request_id,
                    engine=eng,
                    ts=ts,
                    checkouts=stats.checkouts,
                    queries=stats.queries,
                    query_ms=round(stats.query_ms, 3),
                    wait_ms=round(stats.wait_ms, 3),
                    hold_ms=round(stats.hold_ms, 3),
                    total_ms=total_ms_r,
                ),
            )
