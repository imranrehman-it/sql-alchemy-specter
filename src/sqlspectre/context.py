## Per-request timing state shared across ASGI middleware and SQLAlchemy listeners.

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field


@dataclass
class EngineStats:
    checkouts: int = 0
    queries: int = 0
    query_ms: float = 0.0
    wait_ms: float = 0.0
    hold_ms: float = 0.0


@dataclass
class ReqState:
    t0: float
    db_ms: float = 0.0
    query_count: int = 0
    engines: dict[str, EngineStats] = field(default_factory=dict)

    def for_engine(self, eid: str) -> EngineStats:
        stats = self.engines.get(eid)
        if stats is None:
            stats = EngineStats()
            self.engines[eid] = stats
        return stats


request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sqlspectre_request_id", default=None
)
req_state_var: contextvars.ContextVar[ReqState | None] = contextvars.ContextVar(
    "sqlspectre_req", default=None
)
