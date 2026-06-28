"""Small, focused safety helpers used by the MCP tools.

Three guardrails:

* ``safe_eval_math`` — AST-based arithmetic evaluator that replaces ``eval``.
* ``check_url_is_public`` — SSRF protection: resolve a hostname and reject
  loopback, link-local, private, multicast, and reserved addresses.
* ``run_with_timeout`` — run a blocking callable in a thread and abandon it
  after ``timeout`` seconds (used to defuse catastrophic regex backtracking).
"""

from __future__ import annotations

import ast
import concurrent.futures
import ipaddress
import socket
from typing import Any, Callable
from urllib.parse import urlparse

# Math evaluator

# Operators allowed in calculate(). Anything else => SyntaxError.
_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_UNARY_OPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}

# Hard caps to keep eval cheap.
MAX_EXPRESSION_LEN = 200
MAX_POW_EXPONENT = 100  # 9**100 is fine; 9**9**9 would melt the CPU.


class MathError(ValueError):
    """Raised by safe_eval_math for any rejected expression."""


def safe_eval_math(expression: str) -> float | int:
    """Evaluate a simple arithmetic expression safely (no names, no calls).

    Allowed: + - * / // % **, parentheses, unary +/-, int and float literals.
    Raises ``MathError`` for anything else, or if the ** exponent is too big.
    """
    if not isinstance(expression, str):
        raise MathError("expression must be a string")
    if len(expression) > MAX_EXPRESSION_LEN:
        raise MathError(f"expression too long (max {MAX_EXPRESSION_LEN} chars)")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise MathError(f"invalid expression: {e.msg}") from e
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise MathError("only numeric literals are allowed")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise MathError(f"operator {op_type.__name__} not allowed")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_type is ast.Pow:
            # Block giant exponents that would hang the process.
            if isinstance(right, (int, float)) and abs(right) > MAX_POW_EXPONENT:
                raise MathError(f"exponent too large (max {MAX_POW_EXPONENT})")
        return _BIN_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise MathError(f"unary operator {op_type.__name__} not allowed")
        return _UNARY_OPS[op_type](_eval_node(node.operand))
    raise MathError(f"node {type(node).__name__} not allowed")


# SSRF protection

_ALLOWED_SCHEMES = {"http", "https"}


def check_url_is_public(url: str) -> str:
    """Validate that ``url`` points to a public http(s) host.

    Resolves the hostname and rejects loopback / private / link-local /
    multicast / reserved IPs. Returns the (possibly normalized) URL or
    raises ``ValueError`` with a human-readable reason.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("url must be a non-empty string")
    try:
        parsed = urlparse(url)
    except ValueError as e:
        raise ValueError(f"could not parse URL: {e}") from e
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("only http/https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must include a hostname")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"hostname did not resolve: {e}") from e

    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        # Reject anything that isn't a globally routable, non-special IP.
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError(f"host resolves to a non-public address ({addr})")
    return url


# Timeout for blocking calls (e.g. catastrophic regex backtracking)

class TimeoutExceeded(TimeoutError):
    """Raised when ``run_with_timeout`` gives up waiting."""


def run_with_timeout(fn: Callable[..., Any], timeout: float, *args, **kwargs) -> Any:
    """Run ``fn(*args, **kwargs)`` in a worker thread and abandon it after ``timeout`` seconds.

    Note: Python can't actually kill a CPU-bound thread, so the worker keeps
    running in the background. That's acceptable here — we just refuse to
    block the MCP request waiting on it.
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as e:
            raise TimeoutExceeded(f"operation exceeded {timeout}s") from e
    finally:
        # Don't block on the orphaned worker; let it die when the process exits.
        pool.shutdown(wait=False, cancel_futures=True)
