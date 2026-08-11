## Process-wide defaults for sqlspectre.configure() / attach().

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Literal

_FORMATS = frozenset({"ndjson", "csv"})


@dataclass(frozen=True)
class Settings:
    output: str = "./spectate"
    output_format: Literal["ndjson", "csv"] = "ndjson"
    enabled: bool = True
    flush_interval: float = 10.0
    max_buffer: int = 50_000


_settings = Settings()
_FIELD_NAMES = frozenset(f.name for f in fields(Settings))


def get_settings() -> Settings:
    return _settings


def configure(**kwargs: Any) -> Settings:
    """Merge kwargs into process defaults. Unknown keys raise TypeError."""
    global _settings
    unknown = set(kwargs) - _FIELD_NAMES
    if unknown:
        raise TypeError(
            f"configure() got unexpected keyword argument(s): {', '.join(sorted(unknown))}"
        )
    if "output_format" in kwargs and kwargs["output_format"] not in _FORMATS:
        raise ValueError(
            f"output_format must be one of {sorted(_FORMATS)}, "
            f"got {kwargs['output_format']!r}"
        )
    _settings = replace(_settings, **kwargs)
    return _settings


config = configure
