## Buffers events in memory and flushes flat rows (NDJSON or CSV) to disk.

from __future__ import annotations

import atexit
import csv
import json
import threading
from pathlib import Path
from typing import Any, Literal

EVENT_FILES = (
    "recording",
    "request_params",
    "routes",
    "response_size",
    "response_timing",
    "queries",
    "pool_lifecycle",
    "pool_summary",
)


class Recorder:
    def __init__(
        self,
        output: str = "./spectate",
        flush_interval: float = 10.0,
        max_buffer: int = 50_000,
        output_format: Literal["ndjson", "csv"] = "ndjson",
    ) -> None:
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self.output_format = output_format
        ext = "csv" if output_format == "csv" else "ndjson"
        self._active = False
        self._files = {name: self.output / f"{name}.{ext}" for name in EVENT_FILES}
        self._headers_written: set[str] = set()
        self._buf: list[tuple[str, dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._closed = False
        self._thread = threading.Thread(
            target=self._loop, name="sqlspectre-recorder", daemon=True
        )
        self._thread.start()
        atexit.register(self.close)


    def emit(self, kind: str, event: dict[str, Any]) -> None:

        if not self._active:
            return

        try:
            with self._lock:
                if len(self._buf) >= self.max_buffer:
                    return
                self._buf.append((kind, event))
        except Exception:
            pass
    
    def start(self) -> None:
        if self._active:
            return
        self._active = True

    def pause(self) -> None:
        if not self._active:
            return
        self._active = False
        self._flush()

    def _loop(self) -> None:
        while not self._stop.wait(self.flush_interval):
            self._flush()
        self._flush()

    def _flush(self) -> None:
        with self._lock:
            batch = self._buf
            self._buf = []
        if not batch:
            return

        buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in self._files}
        for kind, event in batch:
            buckets[kind].append(event)

        if self.output_format == "csv":
            self._flush_csv(buckets)
        else:
            self._flush_ndjson(buckets)

    def _flush_ndjson(self, buckets: dict[str, list[dict[str, Any]]]) -> None:
        for kind, events in buckets.items():
            if not events:
                continue
            try:
                lines = [
                    json.dumps(e, default=str, separators=(",", ":")) for e in events
                ]
                with self._files[kind].open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except Exception:
                pass

    def _flush_csv(self, buckets: dict[str, list[dict[str, Any]]]) -> None:
        for kind, events in buckets.items():
            if not events:
                continue
            try:
                path = self._files[kind]
                fieldnames = list(events[0].keys())
                # ponytail: header once per file; empty/missing file gets header
                need_header = kind not in self._headers_written and (
                    not path.exists() or path.stat().st_size == 0
                )
                with path.open("a", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=fieldnames, extrasaction="ignore"
                    )
                    if need_header:
                        writer.writeheader()
                        self._headers_written.add(kind)
                    for event in events:
                        writer.writerow(
                            {k: "" if v is None else v for k, v in event.items()}
                        )
            except Exception:
                pass

    



    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self._thread.join(timeout=self.flush_interval + 2)
        self._flush()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        r = Recorder(output=d, flush_interval=0.05, output_format="csv")
        r.emit("recording", {"request_id": "a", "status": 200})
        r.close()
        text = (Path(d) / "recording.csv").read_text()
        assert "request_id,status" in text.splitlines()[0]
        assert "a,200" in text
        r2 = Recorder(output=d, flush_interval=0.05, output_format="ndjson")
        r2.emit("routes", {"request_id": "b", "total_ms": 1.5})
        r2.close()
        assert '"request_id":"b"' in (Path(d) / "routes.ndjson").read_text()
        print("ok")
