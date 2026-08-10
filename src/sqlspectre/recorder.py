"""In-memory buffer → flush to disk every N seconds."""

from __future__ import annotations

import atexit
import json
import threading
from pathlib import Path
from typing import Any


class Recorder:
    """
    Hot path: append event dicts to an in-memory list.
    Background thread: every `flush_interval` seconds, write the batch to disk.
    """

    def __init__(
        self,
        output: str = "./spectate",
        flush_interval: float = 10.0,
        max_buffer: int = 50_000,
    ) -> None:
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer

        self._routes = self.output / "routes.ndjson"
        self._queries = self.output / "queries.ndjson"
        self._engine = self.output / "engine.ndjson"

        self._buf: list[tuple[str, dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._closed = False

        self._thread = threading.Thread(
            target=self._loop,
            name="sqlspectre-recorder",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.close)

    def emit_route(self, event: dict[str, Any]) -> None:
        self._push("routes", event)

    def emit_query(self, event: dict[str, Any]) -> None:
        self._push("queries", event)

    def emit_engine(self, event: dict[str, Any]) -> None:
        self._push("engine", event)

    def _push(self, kind: str, event: dict[str, Any]) -> None:
        try:
            with self._lock:
                if len(self._buf) >= self.max_buffer:
                    return  # drop — fail-open under flood
                self._buf.append((kind, event))
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.wait(self.flush_interval):
            self._flush()
        self._flush()  # final drain on stop

    def _flush(self) -> None:
        with self._lock:
            batch = self._buf
            self._buf = []
        if not batch:
            return

        files = {
            "routes": self._routes,
            "queries": self._queries,
            "engine": self._engine,
        }
        buckets: dict[str, list[str]] = {k: [] for k in files}
        for kind, event in batch:
            try:
                buckets[kind].append(
                    json.dumps(event, default=str, separators=(",", ":"))
                )
            except Exception:
                pass

        for kind, lines in buckets.items():
            if not lines:
                continue
            try:
                with files[kind].open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except Exception:
                pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self._thread.join(timeout=self.flush_interval + 2)
        self._flush()
