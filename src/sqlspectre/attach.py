## Wire an ASGI app to one or more SQLAlchemy engines.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlspectre.engine import instrument_engine
from sqlspectre.middleware import Middleware
from sqlspectre.recorder import Recorder


class SpectreHandle:
    def __init__(self, recorder: Recorder | None) -> None:
        self.recorder = recorder
        self.engines: dict[str, Any] = {}

    def instrument(self, engine: Any, engine_id: str | None = None) -> str | None:
        if self.recorder is None:
            return None
        eid = instrument_engine(engine, self.recorder, engine_id=engine_id)
        self.engines[eid] = engine
        return eid

    def close(self) -> None:
        if self.recorder is not None:
            self.recorder.close()


def _as_pairs(value: Any) -> list[tuple[str | None, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [(str(k), v) for k, v in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [(None, v) for v in value]
    return [(None, value)]


def attach(
    app: Any,
    engine: Any = None,
    *,
    engines: Any = None,
    output: str = "./spectate",
    enabled: bool = True,
) -> SpectreHandle:
    if not enabled:
        return SpectreHandle(None)

    pairs = _as_pairs(engines) + _as_pairs(engine)
    if not pairs:
        raise TypeError("attach() requires at least one engine via engine= or engines=")

    recorder = Recorder(output=output, flush_interval=10.0)
    handle = SpectreHandle(recorder)
    for explicit_id, eng in pairs:
        handle.instrument(eng, engine_id=explicit_id)
    app.add_middleware(Middleware, recorder=recorder)
    return handle
