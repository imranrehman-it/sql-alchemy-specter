## Pull identity and params out of an ASGI request scope.

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import parse_qs

_REDACT = frozenset(
    {"password", "passwd", "secret", "token", "access_token", "refresh_token"}
)
BODY_MAX = 64_000
SKIP_PATHS = frozenset({"/favicon.ico", "/docs", "/redoc", "/openapi.json"})


def headers(scope: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_k, raw_v in scope.get("headers") or ():
        try:
            out[raw_k.decode("latin-1").lower()] = raw_v.decode("latin-1")
        except Exception:
            continue
    return out


def cookies(cookie_header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def query_params(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode() if raw else ""
    if not raw:
        return {}
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if str(k).lower() in _REDACT else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def parse_body(body: bytes, content_type: str) -> Any:
    if not body:
        return None
    ct = content_type.split(";")[0].strip().lower()
    if ct == "application/json":
        try:
            return _redact(json.loads(body.decode()))
        except Exception:
            return None
    if ct == "application/x-www-form-urlencoded":
        try:
            return _redact(query_params(body))
        except Exception:
            return None
    if len(body) <= 512 and ct.startswith("text/"):
        return body.decode(errors="replace")
    return None


def scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, separators=(",", ":"))
    return str(value)


def find_user_id(
    hdrs: dict[str, str],
    cook: dict[str, str],
    query: dict[str, Any],
    path_params: dict[str, Any],
) -> str | None:
    for key in ("x-user-id", "x-userid"):
        if hdrs.get(key):
            return hdrs[key]
    for src in (path_params, query, cook):
        for key in ("user_id", "userid", "uid"):
            val = src.get(key)
            if val is not None and val != "":
                return str(val)
    return None


def session_id(hdrs: dict[str, str], cook: dict[str, str]) -> str | None:
    raw = None
    for key in ("sessionid", "session_id", "sid", "connect.sid", "session"):
        if cook.get(key):
            raw = cook[key]
            break
    if raw is None:
        for key in ("x-session-id", "x-session"):
            if hdrs.get(key):
                raw = hdrs[key]
                break
    if not raw:
        return None
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def iter_params(
    query: dict[str, Any],
    path_params: dict[str, Any],
    body: Any,
):
    for source, mapping in (("query", query), ("path", path_params)):
        for key, value in mapping.items():
            yield source, str(key), scalar(value)
    if isinstance(body, dict):
        for key, value in body.items():
            yield "body", str(key), scalar(value)
    elif body is not None:
        yield "body", "_", scalar(body)
