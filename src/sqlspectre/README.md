## Package layout — see repo root README for install/usage.

```
sqlspectre/
  __init__.py     public API
  attach.py       attach() + SpectreHandle
  middleware.py   ASGI request correlation
  engine.py       SQLAlchemy listeners
  recorder.py     in-memory buffer → NDJSON
  extract.py      headers / params / identity
  context.py      per-request state
  util.py         ids, sql shape, pool cols
  instrument.py   compat re-exports
  cli.py          stub
```
