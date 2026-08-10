"""sqlspectre — attach → record (v0)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlspectre.instrument import Middleware, instrument_engine, resolve_engine_id
from sqlspectre.recorder import Recorder

__all__ = [
    "Middleware",
    "Recorder",
    "SpectreHandle",
    "attach",
    "instrument_engine",
    "resolve_engine_id",
]


class SpectreHandle:
    def __init__(self, recorder: Recorder | None) -> None:
        self.recorder = recorder
        self.engines: dict[str, Any] = {}

    def instrument(self, engine: Any, engine_id: str | None = None) -> str | None:
        """Multi engine attach limited to 2"""
        if self.recorder is None:
            return None
        eid = instrument_engine(engine, self.recorder, engine_id=engine_id)
        self.engines[eid] = engine
        return eid

    def close(self) -> None:
        if self.recorder is not None:
            self.recorder.close()


def _iter_engines(
    engine: Any | None,
    engines: Any | None,
) -> list[tuple[str | None, Any]]:
    """Normalize single/multi engine inputs into (optional_id, engine) pairs."""
    pairs: list[tuple[str | None, Any]] = []

    def add(item: Any, explicit_id: str | None = None) -> None:
        if item is None:
            return
        pairs.append((explicit_id, item))

    if engines is not None:
        if isinstance(engines, Mapping):
            for key, eng in engines.items():
                add(eng, str(key))
        elif isinstance(engines, Sequence) and not isinstance(engines, (str, bytes)):
            for eng in engines:
                add(eng)
        else:
            add(engines)

    if engine is not None:
        if isinstance(engine, Mapping):
            for key, eng in engine.items():
                add(eng, str(key))
        elif isinstance(engine, Sequence) and not isinstance(engine, (str, bytes)):
            for eng in engine:
                add(eng)
        else:
            add(engine)

    return pairs


def attach(
    app: Any,
    engine: Any = None,
    *,
    engines: Any = None,
    output: str = "./spectate",
    enabled: bool = True,
) -> SpectreHandle:
    """
    Attach sqlspectre to an ASGI app and one or more SQLAlchemy engines.

    Examples::

        attach(app, engine)
        attach(app, engines={"primary": e1, "analytics": e2})
        attach(app, engines=[e1, e2])
    """
    if not enabled:
        return SpectreHandle(None)

    pairs = _iter_engines(engine, engines)
    if not pairs:
        raise TypeError("attach() requires at least one engine via engine= or engines=")

    recorder = Recorder(output=output, flush_interval=10.0)
    handle = SpectreHandle(recorder)
    for explicit_id, eng in pairs:
        handle.instrument(eng, engine_id=explicit_id)
    app.add_middleware(Middleware, recorder=recorder)

    return handle
