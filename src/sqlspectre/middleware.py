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
from sqlspectre.rows import (
    pool_summary,
    recording,
    request_params,
    response_size,
    response_timing,
    routes,
)
from sqlspectre.util import new_id

_json_encode_patched = False


def _patch_json_encode() -> None:
    global _json_encode_patched
    if _json_encode_patched:
        return
    try:
        from starlette.responses import JSONResponse
    except Exception:
        return

    orig = JSONResponse.render

    def render(self, content):  # type: ignore[no-untyped-def]
        state = req_state_var.get()
        if state is None:
            return orig(self, content)
        t0 = time.perf_counter()
        try:
            return orig(self, content)
        finally:
            state.encode_ms += (time.perf_counter() - t0) * 1000

    JSONResponse.render = render  # type: ignore[method-assign]
    _json_encode_patched = True


class Middleware:
    def __init__(self, app: Callable, recorder: Recorder | None = None) -> None:
        self.app = app
        self.recorder = recorder
        _patch_json_encode()

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
        t_response_end: float | None = None
        response_body_len = 0
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
            nonlocal status, t_response_start, t_response_end, response_body_len
            if message["type"] == "http.response.start":
                status = message["status"]
                t_response_start = time.perf_counter()
            elif message["type"] == "http.response.body":
                try:
                    response_body_len += len(message.get("body") or b"")
                except Exception:
                    pass
                await send(message)
                t_response_end = time.perf_counter()
                return
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
                    t_response_end,
                    bytes(body_buf),
                    response_body_len,
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
        t_response_end: float | None,
        body_bytes: bytes,
        response_body_len: int,
        path: str,
    ) -> None:
        assert self.recorder is not None
        total_ms = (time.perf_counter() - state.t0) * 1000
        ttfb_ms = (
            (t_response_start - state.t0) * 1000
            if t_response_start is not None
            else total_ms
        )
        send_ms = (
            (t_response_end - t_response_start) * 1000
            if t_response_start is not None and t_response_end is not None
            else 0.0
        )
        response_ms = max(0.0, total_ms - ttfb_ms)
        # build = handler work before encode (excludes db + JSONResponse.render)
        build_ms = max(0.0, ttfb_ms - state.db_ms - state.encode_ms)
        process_ms = max(0.0, ttfb_ms - state.db_ms)

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
        self.recorder.emit(
            "response_size",
            response_size(
                request_id=request_id,
                response_bytes=response_body_len,
            ),
        )
        self.recorder.emit(
            "response_timing",
            response_timing(
                request_id=request_id,
                build_ms=round(build_ms, 3),
                encode_ms=round(state.encode_ms, 3),
                send_ms=round(send_ms, 3),
            ),
        )
