from fastmcp import FastMCP
import base64
import datetime
import hashlib
import json
import random
import re
import secrets
import string
import uuid
from urllib.parse import urlparse

import httpx

mcp = FastMCP("Local MCP Server")

# Shared HTTP client config used by network tools
_HTTP_TIMEOUT = 10.0
_HTTP_MAX_BYTES = 200_000  # cap response bodies returned to the model
_HTTP_USER_AGENT = "sample-mcp-server/0.2 (+https://modelcontextprotocol.io)"

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


# ---------------------------------------------------------------------------
# Encoding / hashing utilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Identifiers & secrets
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JSON & regex helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Network tools
# ---------------------------------------------------------------------------

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


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)