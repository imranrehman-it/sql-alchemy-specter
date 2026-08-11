## Buffer events in memory and flush flat rows (NDJSON or CSV) to disk.

from __future__ import annotations

import atexit
import csv
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlspectre.util import new_id

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

Status = Literal["running", "paused", "stopped"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass
class Recording:
    """One start→stop session. pause/resume keep the same id."""

    id: str
    started_at: str
    output: str
    status: Status = "running"
    ended_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Recorder:
    def __init__(
        self,
        output: str = "./spectate",
        flush_interval: float = 10.0,
        max_buffer: int = 50_000,
        output_format: Literal["ndjson", "csv"] = "ndjson",
    ) -> None:
        self.output_root = Path(output)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self.output_format = output_format
        self._ext = "csv" if output_format == "csv" else "ndjson"

        self._recording: Recording | None = None
        self._files: dict[str, Path] = {}
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

    # --- public state -------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._recording is not None and self._recording.status == "running"

    @property
    def is_paused(self) -> bool:
        return self._recording is not None and self._recording.status == "paused"

    @property
    def current(self) -> Recording | None:
        return self._recording

    def details(self) -> dict[str, Any]:
        """Public snapshot of the current (or last) recording + recorder config."""
        rec = self._recording.to_dict() if self._recording else None
        return {
            "recording": rec,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "buffer_size": len(self._buf),
            "max_buffer": self.max_buffer,
            "flush_interval": self.flush_interval,
            "output_root": str(self.output_root),
            "output_format": self.output_format,
        }

    # keep old name so callers don't break
    get_details = details

    # --- lifecycle ----------------------------------------------------------

    def start(self) -> dict[str, Any]:
        """Start a new recording, or resume if paused.

        Raises RuntimeError if a recording is already running.
        """
        if self._closed:
            raise RuntimeError("recorder is closed")

        if self.is_running:
            raise RuntimeError(
                f"recording already running (id={self._recording.id})"
            )

        if self.is_paused:
            assert self._recording is not None
            self._recording.status = "running"
            return self._recording.to_dict()

        # new session → own subfolder: {id}_{YYYY-MM-DD}
        rid = new_id()
        started = _utc_now()
        folder = self.output_root / f"{rid}_{started.strftime('%Y-%m-%d')}"
        folder.mkdir(parents=True, exist_ok=True)

        self._recording = Recording(
            id=rid,
            started_at=_iso(started),
            output=str(folder),
            status="running",
        )
        self._bind_output(folder)
        return self._recording.to_dict()

    def pause(self) -> dict[str, Any] | None:
        """Pause the current recording (same id; start() resumes)."""
        if not self.is_running:
            return self._recording.to_dict() if self._recording else None

        assert self._recording is not None
        self._recording.status = "paused"
        self._flush()
        return self._recording.to_dict()

    def stop(self) -> dict[str, Any] | None:
        """End the current recording. Next start() opens a new session."""
        if self._recording is None or self._recording.status == "stopped":
            return self._recording.to_dict() if self._recording else None

        self._recording.status = "stopped"
        self._recording.ended_at = _iso(_utc_now())
        self._flush()
        self._write_meta(self._recording)
        return self._recording.to_dict()

    def emit(self, kind: str, event: dict[str, Any]) -> None:
        if not self.is_running:
            return
        try:
            with self._lock:
                if len(self._buf) >= self.max_buffer:
                    return
                self._buf.append((kind, event))
        except Exception:
            pass

    def close(self) -> None:
        """Shut down the flush thread (process exit). Stops any open recording."""
        if self._closed:
            return
        self._closed = True
        if self._recording and self._recording.status != "stopped":
            self.stop()
        self._stop.set()
        self._thread.join(timeout=self.flush_interval + 2)
        self._flush()

    # --- internals ----------------------------------------------------------

    def _bind_output(self, folder: Path) -> None:
        self._files = {name: folder / f"{name}.{self._ext}" for name in EVENT_FILES}
        self._headers_written = set()

    def _write_meta(self, recording: Recording) -> None:
        try:
            path = Path(recording.output) / "meta.json"
            path.write_text(
                json.dumps(recording.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.wait(self.flush_interval):
            self._flush()
        self._flush()

    def _flush(self) -> None:
        with self._lock:
            batch = self._buf
            self._buf = []
        if not batch or not self._files:
            return

        buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in self._files}
        for kind, event in batch:
            buckets.setdefault(kind, []).append(event)

        if self.output_format == "csv":
            self._flush_csv(buckets)
        else:
            self._flush_ndjson(buckets)

    def _flush_ndjson(self, buckets: dict[str, list[dict[str, Any]]]) -> None:
        for kind, events in buckets.items():
            if not events or kind not in self._files:
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
            if not events or kind not in self._files:
                continue
            try:
                path = self._files[kind]
                fieldnames = list(events[0].keys())
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


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        r = Recorder(output=d, flush_interval=0.05, output_format="csv")
        info = r.start()
        assert info["status"] == "running"
        assert Path(info["output"]).is_dir()
        r.emit("recording", {"request_id": "a", "status": 200})
        try:
            r.start()
            raise AssertionError("expected already-running")
        except RuntimeError:
            pass
        r.pause()
        assert r.details()["is_paused"]
        r.start()  # resume
        assert r.current and r.current.id == info["id"]
        stopped = r.stop()
        assert stopped and stopped["ended_at"]
        assert (Path(stopped["output"]) / "meta.json").exists()
        again = r.start()
        assert again["id"] != info["id"]
        r.close()
        print("ok")
