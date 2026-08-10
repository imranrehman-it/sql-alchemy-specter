## Compatibility shim — prefer sqlspectre.engine / sqlspectre.middleware.

from sqlspectre.engine import instrument_engine
from sqlspectre.middleware import Middleware
from sqlspectre.util import resolve_engine_id

__all__ = ["Middleware", "instrument_engine", "resolve_engine_id"]
