from fastmcp import FastMCP
import argparse
import base64
import datetime
import hashlib
import json
import logging
import os
import random
import re
import secrets
import string
import uuid
from urllib.parse import urlparse

import httpx

from .notes_db import NotesDB

# Server config

SERVER_NAME = "Local MCP Server"
SERVER_VERSION = "0.3.0"
SERVER_START_TIME = datetime.datetime.now(datetime.timezone.utc)

_HTTP_TIMEOUT = 10.0
_HTTP_MAX_BYTES = 200_000  # cap response bodies returned to the model
_HTTP_USER_AGENT = f"sample-mcp-server/{SERVER_VERSION} (+https://modelcontextprotocol.io)"

NOTES_DB_PATH = os.environ.get("MCP_NOTES_DB", "data/notes.db")

logger = logging.getLogger("mcp.server")

mcp = FastMCP(SERVER_NAME)
notes = NotesDB(NOTES_DB_PATH)

@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a safe math expression. Example: '2 + 2 * 10'"""
    try:
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operators allowed."
        result = eval(expression, {"__builtins__": {}})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def get_server_time() -> str:
    """Returns the current server date and time."""
    now = datetime.datetime.utcnow()
    return f"Server time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}"

@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number between min_val and max_val."""
    if min_val >= max_val:
        return "Error: min_val must be less than max_val."
    num = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {num}"

@mcp.tool()
def analyze_text(text: str) -> dict:
    """Analyze a given text and return word count, char count, and sentences."""
    words = text.split()
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "characters": len(text),
        "words": len(words),
        "sentences": len(sentences),
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0
    }

@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message. Useful for testing connectivity."""
    return f"[MCP Server Echo]: {message}"


# Encoding / hashing utilities

@mcp.tool()
def hash_text(text: str, algorithm: str = "sha256") -> dict:
    """Hash a string with md5, sha1, sha256, or sha512.

    Args:
        text: The text to hash.
        algorithm: One of 'md5', 'sha1', 'sha256', 'sha512'. Defaults to 'sha256'.
    """
    algo = algorithm.lower().strip()
    supported = {"md5", "sha1", "sha256", "sha512"}
    if algo not in supported:
        return {"error": f"Unsupported algorithm '{algorithm}'. Choose one of: {sorted(supported)}"}
    digest = hashlib.new(algo, text.encode("utf-8")).hexdigest()
    return {"algorithm": algo, "input_length": len(text), "hex": digest}


@mcp.tool()
def base64_encode(text: str, url_safe: bool = False) -> str:
    """Base64-encode a UTF-8 string. Set url_safe=True for URL-safe alphabet."""
    data = text.encode("utf-8")
    encoded = base64.urlsafe_b64encode(data) if url_safe else base64.b64encode(data)
    return encoded.decode("ascii")


@mcp.tool()
def base64_decode(data: str, url_safe: bool = False) -> str:
    """Decode a base64 string back to UTF-8 text."""
    try:
        raw = base64.urlsafe_b64decode(data) if url_safe else base64.b64decode(data, validate=True)
        return raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as e:
        return f"Error: invalid base64 input ({e})"


# Identifiers & secrets

@mcp.tool()
def uuid_generate(count: int = 1, version: int = 4) -> dict:
    """Generate one or more UUIDs.

    Args:
        count: How many UUIDs to generate (1-100).
        version: UUID version. Only 4 (random) and 1 (time-based) are supported.
    """
    if not 1 <= count <= 100:
        return {"error": "count must be between 1 and 100"}
    if version == 4:
        ids = [str(uuid.uuid4()) for _ in range(count)]
    elif version == 1:
        ids = [str(uuid.uuid1()) for _ in range(count)]
    else:
        return {"error": "Only UUID versions 1 and 4 are supported"}
    return {"version": version, "count": count, "uuids": ids}


@mcp.tool()
def password_generate(
    length: int = 20,
    use_uppercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
) -> dict:
    """Generate a cryptographically strong random password.

    Always includes lowercase letters. Toggle the other categories.
    """
    if not 8 <= length <= 128:
        return {"error": "length must be between 8 and 128"}

    alphabet = string.ascii_lowercase
    required: list[str] = [secrets.choice(string.ascii_lowercase)]
    if use_uppercase:
        alphabet += string.ascii_uppercase
        required.append(secrets.choice(string.ascii_uppercase))
    if use_digits:
        alphabet += string.digits
        required.append(secrets.choice(string.digits))
    if use_symbols:
        symbols = "!@#$%^&*()-_=+[]{};:,.?/"
        alphabet += symbols
        required.append(secrets.choice(symbols))

    remaining = [secrets.choice(alphabet) for _ in range(length - len(required))]
    pwd_chars = required + remaining
    # Shuffle without bias using secrets
    for i in range(len(pwd_chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pwd_chars[i], pwd_chars[j] = pwd_chars[j], pwd_chars[i]

    return {"length": length, "password": "".join(pwd_chars)}


# JSON & regex helpers

@mcp.tool()
def json_format(data: str, indent: int = 2, sort_keys: bool = False) -> str:
    """Pretty-print a JSON string. Returns an error message if input isn't valid JSON."""
    if not 0 <= indent <= 8:
        return "Error: indent must be between 0 and 8"
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON ({e.msg} at line {e.lineno} col {e.colno})"
    return json.dumps(parsed, indent=indent, sort_keys=sort_keys, ensure_ascii=False)


@mcp.tool()
def regex_match(pattern: str, text: str, ignore_case: bool = False, multiline: bool = False) -> dict:
    """Find all matches of a regex pattern in text.

    Returns the first 50 matches along with their start/end offsets and any groups.
    """
    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"invalid regex: {e}"}

    matches = []
    for m in compiled.finditer(text):
        matches.append({
            "match": m.group(0),
            "start": m.start(),
            "end": m.end(),
            "groups": list(m.groups()),
        })
        if len(matches) >= 50:
            break
    return {"pattern": pattern, "count": len(matches), "matches": matches}


# Unit conversion

# All length units in metres, all weight units in grams.
_LENGTH_TO_M = {
    "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
    "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
}
_WEIGHT_TO_G = {
    "mg": 0.001, "g": 1.0, "kg": 1000.0, "t": 1_000_000.0,
    "oz": 28.3495, "lb": 453.592,
}


@mcp.tool()
def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert a numeric value between units.

    Supported categories:
      - length: mm, cm, m, km, in, ft, yd, mi
      - weight: mg, g, kg, t, oz, lb
      - temperature: C, F, K
    """
    f = from_unit.strip()
    t = to_unit.strip()

    # Temperature is a special case (affine, not just scaling)
    temp_units = {"C", "F", "K"}
    if f in temp_units or t in temp_units:
        if f not in temp_units or t not in temp_units:
            return {"error": "Cannot mix temperature with non-temperature units"}
        # to Kelvin first
        if f == "C":
            k = value + 273.15
        elif f == "F":
            k = (value - 32) * 5 / 9 + 273.15
        else:
            k = value
        if t == "C":
            out = k - 273.15
        elif t == "F":
            out = (k - 273.15) * 9 / 5 + 32
        else:
            out = k
        return {"value": value, "from": f, "to": t, "result": round(out, 6), "category": "temperature"}

    if f.lower() in _LENGTH_TO_M and t.lower() in _LENGTH_TO_M:
        metres = value * _LENGTH_TO_M[f.lower()]
        out = metres / _LENGTH_TO_M[t.lower()]
        return {"value": value, "from": f, "to": t, "result": round(out, 6), "category": "length"}

    if f.lower() in _WEIGHT_TO_G and t.lower() in _WEIGHT_TO_G:
        grams = value * _WEIGHT_TO_G[f.lower()]
        out = grams / _WEIGHT_TO_G[t.lower()]
        return {"value": value, "from": f, "to": t, "result": round(out, 6), "category": "weight"}

    return {"error": f"Unsupported or mismatched units: '{from_unit}' -> '{to_unit}'"}


# Network tools

def _safe_url(url: str) -> tuple[bool, str]:
    """Allow only http(s) URLs with a hostname. Returns (ok, reason)."""
    try:
        parsed = urlparse(url)
    except ValueError as e:
        return False, f"could not parse URL: {e}"
    if parsed.scheme not in {"http", "https"}:
        return False, "only http/https URLs are allowed"
    if not parsed.hostname:
        return False, "URL must include a hostname"
    return True, ""


@mcp.tool()
def fetch_url(url: str, method: str = "GET", max_bytes: int = _HTTP_MAX_BYTES) -> dict:
    """Fetch an http(s) URL and return status, headers, and a truncated body.

    Args:
        url: Absolute http or https URL.
        method: 'GET' or 'HEAD'. Defaults to 'GET'.
        max_bytes: Cap on the body size returned (default 200 KB, max 1 MB).
    """
    ok, reason = _safe_url(url)
    if not ok:
        return {"error": reason}
    m = method.upper()
    if m not in {"GET", "HEAD"}:
        return {"error": "method must be 'GET' or 'HEAD'"}
    cap = max(1024, min(int(max_bytes), 1_000_000))

    try:
        with httpx.Client(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _HTTP_USER_AGENT},
        ) as client:
            resp = client.request(m, url)
    except httpx.HTTPError as e:
        return {"error": f"request failed: {e}"}

    body = resp.content[:cap]
    truncated = len(resp.content) > cap
    try:
        text = body.decode(resp.encoding or "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")

    return {
        "url": str(resp.url),
        "status": resp.status_code,
        "reason": resp.reason_phrase,
        "headers": dict(resp.headers),
        "bytes_total": len(resp.content),
        "bytes_returned": len(body),
        "truncated": truncated,
        "body": text if m == "GET" else "",
    }


@mcp.tool()
def weather(latitude: float, longitude: float) -> dict:
    """Get the current weather for a lat/lon using the free Open-Meteo API (no key needed)."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return {"error": "latitude must be in [-90, 90] and longitude in [-180, 180]"}
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code"
    )
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": _HTTP_USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"weather lookup failed: {e}"}
    except ValueError:
        return {"error": "weather API returned non-JSON response"}

    current = payload.get("current", {})
    units = payload.get("current_units", {})
    return {
        "latitude": payload.get("latitude", latitude),
        "longitude": payload.get("longitude", longitude),
        "timezone": payload.get("timezone"),
        "observed_at": current.get("time"),
        "temperature": current.get("temperature_2m"),
        "temperature_unit": units.get("temperature_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_speed_unit": units.get("wind_speed_10m"),
        "humidity": current.get("relative_humidity_2m"),
        "humidity_unit": units.get("relative_humidity_2m"),
        "weather_code": current.get("weather_code"),
    }


# ---------------------------------------------------------------------------
# Notes — stateful CRUD demo backed by SQLite (see notes_db.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def note_add(title: str, body: str = "") -> dict:
    """Create a new note. Returns the saved note including its id and timestamps."""
    try:
        return notes.add(title, body)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def note_list(limit: int = 50, search: str | None = None) -> dict:
    """List recent notes (newest first). Optional case-insensitive substring search."""
    items = notes.list(limit=limit, search=search)
    return {"count": len(items), "total": notes.count(), "notes": items}


@mcp.tool()
def note_get(note_id: int) -> dict:
    """Fetch a single note by id."""
    note = notes.get(note_id)
    return note if note else {"error": f"note {note_id} not found"}


@mcp.tool()
def note_update(note_id: int, title: str | None = None, body: str | None = None) -> dict:
    """Update a note's title and/or body. At least one of title/body must be given."""
    try:
        updated = notes.update(note_id, title=title, body=body)
    except ValueError as e:
        return {"error": str(e)}
    return updated if updated else {"error": f"note {note_id} not found"}


@mcp.tool()
def note_delete(note_id: int) -> dict:
    """Delete a note by id."""
    ok = notes.delete(note_id)
    return {"deleted": ok, "id": note_id}


# ---------------------------------------------------------------------------
# MCP Resources — read-only data that clients can subscribe to or fetch.
# ---------------------------------------------------------------------------

@mcp.resource("resource://server/info")
def resource_server_info() -> dict:
    """Server metadata: name, version, uptime, and tool/resource/prompt counts."""
    now = datetime.datetime.now(datetime.timezone.utc)
    uptime = (now - SERVER_START_TIME).total_seconds()
    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "started_at": SERVER_START_TIME.isoformat(),
        "uptime_seconds": round(uptime, 1),
        "python": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
        "notes_db_path": NOTES_DB_PATH,
        "notes_count": notes.count(),
    }


@mcp.resource("resource://notes/all")
def resource_notes_all() -> dict:
    """All notes currently stored (newest first, max 500)."""
    return {"notes": notes.list(limit=500)}


@mcp.resource("resource://notes/{note_id}")
def resource_note(note_id: str) -> dict:
    """Fetch a single note as a resource (path: resource://notes/<id>)."""
    try:
        nid = int(note_id)
    except ValueError:
        return {"error": f"invalid note id: {note_id!r}"}
    note = notes.get(nid)
    return note if note else {"error": f"note {nid} not found"}


# ---------------------------------------------------------------------------
# MCP Prompts — reusable prompt templates clients can pick from a menu.
# ---------------------------------------------------------------------------

@mcp.prompt()
def summarize_text(text: str, style: str = "concise") -> str:
    """Ask the model to summarize a chunk of text in a chosen style."""
    return (
        f"Summarize the following text in a {style} style. "
        "Preserve key facts, names, and numbers. Output plain prose only.\n\n"
        f"---\n{text}\n---"
    )


@mcp.prompt()
def code_review(code: str, language: str = "python") -> str:
    """Ask the model for a structured code review of a snippet."""
    return (
        f"You are a senior {language} engineer. Review the following code.\n"
        "Reply with three sections:\n"
        "  1. **Bugs / correctness issues** (with line refs)\n"
        "  2. **Security concerns** (OWASP-style)\n"
        "  3. **Suggested improvements** (readability, performance, idiomatic style)\n\n"
        f"```{language}\n{code}\n```"
    )


@mcp.prompt()
def explain_error(error_message: str, context: str = "") -> str:
    """Ask the model to explain an error message and suggest fixes."""
    ctx = f"\nRelevant context:\n{context}\n" if context.strip() else ""
    return (
        "Explain the following error message in plain language, then list the most "
        "likely causes and concrete steps to fix it.\n\n"
        f"Error:\n{error_message}\n{ctx}"
    )


# ---------------------------------------------------------------------------
# CLI / entrypoint
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{SERVER_NAME} v{SERVER_VERSION}")
    p.add_argument("--transport", choices=["sse", "stdio", "http"],
                   default=os.environ.get("MCP_TRANSPORT", "sse"),
                   help="Transport to expose (default: sse).")
    p.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"),
                   help="Bind host for sse/http transports (default: 0.0.0.0).")
    p.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")),
                   help="Bind port for sse/http transports (default: 8000).")
    p.add_argument("--log-level", default=os.environ.get("MCP_LOG_LEVEL", "INFO"),
                   choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                   help="Logging verbosity (default: INFO).")
    p.add_argument("--log-file", default=os.environ.get("MCP_LOG_FILE"),
                   help="Optional path to also write logs to a file.")
    p.add_argument("--version", action="version", version=f"%(prog)s {SERVER_VERSION}")
    return p


def _configure_logging(level: str, log_file: str | None) -> None:
    fmt = "%(asctime)s %(levelname)-5s %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.log_level, args.log_file)
    logger.info("starting %s v%s transport=%s", SERVER_NAME, SERVER_VERSION, args.transport)
    logger.info("notes_db=%s notes_count=%d", NOTES_DB_PATH, notes.count())

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())