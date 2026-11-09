"""Everyday DevTools MCP server.

A zero-dependency MCP (Model Context Protocol) server that gives AI
assistants 17 small tools developers reach for every day: encoders,
hashing, JSON helpers, JWT decoding, UUIDs, timestamps, cron schedules,
regex testing, passwords, colour conversion and text stats.

Runs over stdio using newline-delimited JSON-RPC 2.0 (MCP 2024-11-05).
No third-party packages required. Python 3.10+.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import string
import sys
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

SERVER_NAME = "everyday-devtools-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


# --------------------------------------------------------------------------
# Tool implementations. Each returns a plain string result.
# --------------------------------------------------------------------------

def _b64_encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _b64_decode(text: str) -> str:
    try:
        return base64.b64decode(text.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid base64 input: {exc}") from exc


def _url_encode(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def _url_decode(text: str) -> str:
    return urllib.parse.unquote_plus(text)


def _uuid_generate(count: int = 1) -> str:
    count = max(1, min(int(count), 100))
    return "\n".join(str(uuid.uuid4()) for _ in range(count))


def _hash_text(text: str, algorithm: str = "sha256") -> str:
    algo = algorithm.lower()
    if algo not in ("md5", "sha1", "sha256", "sha512"):
        raise ValueError("algorithm must be one of: md5, sha1, sha256, sha512")
    return hashlib.new(algo, text.encode("utf-8")).hexdigest()


def _json_format(text: str, indent: int = 2) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return json.dumps(data, indent=int(indent), ensure_ascii=False)


def _json_minify(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _b64url_decode(segment: str) -> bytes:
    segment += "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment)


def _jwt_decode(token: str) -> str:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("a JWT must have 3 dot-separated parts")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception as exc:  # noqa: BLE001 - report any decode failure plainly
        raise ValueError(f"could not decode JWT: {exc}") from exc
    notes = []
    if "exp" in payload:
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        state = "EXPIRED" if exp < datetime.now(timezone.utc) else "still valid"
        notes.append(f"exp: {exp.isoformat()} ({state})")
    return (
        "HEADER:\n" + json.dumps(header, indent=2)
        + "\n\nPAYLOAD:\n" + json.dumps(payload, indent=2)
        + ("\n\n" + "\n".join(notes) if notes else "")
        + "\n\nNote: signature is NOT verified by this tool."
    )


def _timestamp_convert(value: str) -> str:
    value = value.strip()
    # Unix seconds (or milliseconds) -> human readable
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        num = float(value)
        if abs(num) > 1e12:  # treat as milliseconds
            num /= 1000.0
        dt = datetime.fromtimestamp(num, tz=timezone.utc)
        return f"Unix {int(num)} = {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC ({dt.isoformat()})"
    # ISO-ish date string -> Unix
    cleaned = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"unrecognised timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"{value} = Unix {int(dt.timestamp())} ({dt.astimezone(timezone.utc).isoformat()} UTC)"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _text_stats(text: str) -> str:
    words = re.findall(r"\S+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    return json.dumps(
        {
            "characters": len(text),
            "characters_no_spaces": len(text.replace(" ", "")),
            "words": len(words),
            "lines": text.count("\n") + 1 if text else 0,
            "sentences": len(sentences),
        },
        indent=2,
    )


def _password_generate(length: int = 16, symbols: bool = True) -> str:
    length = max(8, min(int(length), 128))
    alphabet = string.ascii_letters + string.digits
    if symbols:
        alphabet += "!@#$%^&*()-_=+[]{}<>?"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and (not symbols or any(not c.isalnum() for c in pw))
        ):
            return pw


def _parse_cron_field(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step < 1:
                raise ValueError("cron step must be >= 1")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(part)
        if start < low or end > high or start > end:
            raise ValueError(f"cron value out of range ({low}-{high}): {field}")
        values.update(range(start, end + 1, step))
    return values


def _cron_next(expression: str, count: int = 5) -> str:
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError("expected a standard 5-field cron expression")
    minutes = _parse_cron_field(fields[0], 0, 59)
    hours = _parse_cron_field(fields[1], 0, 23)
    doms = _parse_cron_field(fields[2], 1, 31)
    months = _parse_cron_field(fields[3], 1, 12)
    dows = _parse_cron_field(fields[4], 0, 7)
    dows = {0 if d == 7 else d for d in dows}  # cron: 0 and 7 both mean Sunday

    count = max(1, min(int(count), 25))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    cursor = now + timedelta(minutes=1)
    found: list[str] = []
    for _ in range(366 * 24 * 60):  # scan at most ~1 year ahead
        cron_dow = (cursor.weekday() + 1) % 7  # Python Mon=0 -> cron Sun=0
        if (
            cursor.minute in minutes
            and cursor.hour in hours
            and cursor.day in doms
            and cursor.month in months
            and cron_dow in dows
        ):
            found.append(cursor.strftime("%Y-%m-%d %H:%M UTC"))
            if len(found) >= count:
                break
        cursor += timedelta(minutes=1)
    if not found:
        raise ValueError("no matching run time within the next year")
    return "Next runs (UTC):\n" + "\n".join(found)


def _regex_test(pattern: str, text: str) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex: {exc}") from exc
    matches = [m.group(0) for m in rx.finditer(text)]
    return json.dumps({"match_count": len(matches), "matches": matches[:50]}, indent=2)


def _color_convert(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        hexpart = value.lstrip("#")
        r, g, b = (int(hexpart[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{hexpart.upper()} = rgb({r}, {g}, {b})"
    m = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    if m:
        r, g, b = (int(x) for x in m.groups())
        if max(r, g, b) > 255:
            raise ValueError("rgb components must be 0-255")
        return f"rgb({r}, {g}, {b}) = #{r:02X}{g:02X}{b:02X}"
    raise ValueError("expected a hex colour like #1A2B3C or rgb(26, 43, 60)")


def _case_convert(text: str, mode: str = "upper") -> str:
    mode = mode.lower()
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return text.title()
    if mode == "snake":
        return _slugify(text).replace("-", "_")
    if mode == "kebab":
        return _slugify(text)
    if mode == "camel":
        parts = _slugify(text).split("-")
        return parts[0] + "".join(p.title() for p in parts[1:]) if parts else ""
    raise ValueError("mode must be one of: upper, lower, title, snake, kebab, camel")


# --------------------------------------------------------------------------
# Tool registry: name -> (description, JSON schema, function, arg order)
# --------------------------------------------------------------------------

def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


_TEXT = {"type": "string"}

TOOLS: dict[str, dict] = {
    "base64_encode": {
        "description": "Encode text to Base64.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _b64_encode(a["text"]),
    },
    "base64_decode": {
        "description": "Decode a Base64 string back to text.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _b64_decode(a["text"]),
    },
    "url_encode": {
        "description": "Percent-encode text for use in a URL.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _url_encode(a["text"]),
    },
    "url_decode": {
        "description": "Decode a percent-encoded URL string.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _url_decode(a["text"]),
    },
    "uuid_generate": {
        "description": "Generate one or more random UUID v4 values.",
        "inputSchema": _schema(
            {"count": {"type": "integer", "default": 1, "minimum": 1, "maximum": 100}}, []
        ),
        "fn": lambda a: _uuid_generate(a.get("count", 1)),
    },
    "hash_text": {
        "description": "Hash text with md5, sha1, sha256 or sha512.",
        "inputSchema": _schema(
            {"text": _TEXT, "algorithm": {"type": "string", "default": "sha256"}},
            ["text"],
        ),
        "fn": lambda a: _hash_text(a["text"], a.get("algorithm", "sha256")),
    },
    "json_format": {
        "description": "Validate and pretty-print a JSON string.",
        "inputSchema": _schema(
            {"text": _TEXT, "indent": {"type": "integer", "default": 2}}, ["text"]
        ),
        "fn": lambda a: _json_format(a["text"], a.get("indent", 2)),
    },
    "json_minify": {
        "description": "Validate and minify a JSON string to one line.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _json_minify(a["text"]),
    },
    "jwt_decode": {
        "description": "Decode a JWT header and payload (signature is not verified).",
        "inputSchema": _schema({"token": _TEXT}, ["token"]),
        "fn": lambda a: _jwt_decode(a["token"]),
    },
    "timestamp_convert": {
        "description": "Convert a Unix timestamp (seconds or ms) to a UTC date, or an ISO date string to a Unix timestamp.",
        "inputSchema": _schema({"value": _TEXT}, ["value"]),
        "fn": lambda a: _timestamp_convert(a["value"]),
    },
    "slugify": {
        "description": "Turn text into a URL-safe slug.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _slugify(a["text"]),
    },
    "text_stats": {
        "description": "Count characters, words, lines and sentences in text.",
        "inputSchema": _schema({"text": _TEXT}, ["text"]),
        "fn": lambda a: _text_stats(a["text"]),
    },
    "password_generate": {
        "description": "Generate a strong random password (cryptographically secure).",
        "inputSchema": _schema(
            {
                "length": {"type": "integer", "default": 16, "minimum": 8, "maximum": 128},
                "symbols": {"type": "boolean", "default": True},
            },
            [],
        ),
        "fn": lambda a: _password_generate(a.get("length", 16), a.get("symbols", True)),
    },
    "cron_next": {
        "description": "Show the next run times (UTC) for a standard 5-field cron expression.",
        "inputSchema": _schema(
            {"expression": _TEXT, "count": {"type": "integer", "default": 5}},
            ["expression"],
        ),
        "fn": lambda a: _cron_next(a["expression"], a.get("count", 5)),
    },
    "regex_test": {
        "description": "Test a regular expression against text and list all matches.",
        "inputSchema": _schema({"pattern": _TEXT, "text": _TEXT}, ["pattern", "text"]),
        "fn": lambda a: _regex_test(a["pattern"], a["text"]),
    },
    "color_convert": {
        "description": "Convert a colour between hex (#1A2B3C) and rgb(26, 43, 60) forms.",
        "inputSchema": _schema({"value": _TEXT}, ["value"]),
        "fn": lambda a: _color_convert(a["value"]),
    },
    "case_convert": {
        "description": "Convert text case: upper, lower, title, snake_case, kebab-case or camelCase.",
        "inputSchema": _schema(
            {"text": _TEXT, "mode": {"type": "string", "default": "upper"}},
            ["text"],
        ),
        "fn": lambda a: _case_convert(a["text"], a.get("mode", "upper")),
    },
}


# --------------------------------------------------------------------------
# Minimal MCP stdio transport (newline-delimited JSON-RPC 2.0)
# --------------------------------------------------------------------------

def _result(req_id, payload) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": payload}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {
            "tools": [
                {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["inputSchema"],
                }
                for name, spec in TOOLS.items()
            ]
        })
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if spec is None:
            return _result(req_id, {
                "content": [{"type": "text", "text": f"unknown tool: {name}"}],
                "isError": True,
            })
        try:
            output = spec["fn"](arguments)
        except (ValueError, KeyError, TypeError) as exc:
            return _result(req_id, {
                "content": [{"type": "text", "text": f"error: {exc}"}],
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text", "text": str(output)}],
            "isError": False,
        })
    return _error(req_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
