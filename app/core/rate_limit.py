"""
app/core/rate_limit.py
-----------------------
In-memory login rate limiter.

Limit: 5 failed attempts per IP per 60-second sliding window → 429.
Resets on successful login.

⚠️  V1 LIMITATION: This in-memory store does not survive process restarts
and will not work correctly if the backend runs with multiple workers or
across multiple instances (e.g., behind a load balancer). For V2, replace
with a Redis-backed implementation (e.g., slowapi + Redis, or a custom
Redis sliding-window counter).
"""

import time
from typing import TypedDict

# In-memory store: ip -> {"count": int, "window_start": float}
_login_attempts: dict[str, dict] = {}

# Configuration constants — adjust here, not per call-site.
MAX_ATTEMPTS: int = 5
WINDOW_SECONDS: int = 60


def _get_bucket(ip: str) -> dict:
    """Return (and lazily create) the rate-limit bucket for the given IP."""
    now = time.time()
    bucket = _login_attempts.get(ip)

    if bucket is None or (now - bucket["window_start"]) >= WINDOW_SECONDS:
        # New IP or window has expired — reset.
        _login_attempts[ip] = {"count": 0, "window_start": now}

    return _login_attempts[ip]


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """
    Check whether the IP is within the allowed rate limit.

    Returns:
        (allowed: bool, retry_after: int)
        - allowed=True  → request may proceed
        - allowed=False → request must be rejected with 429;
          retry_after is seconds until the window resets.
    """
    bucket = _get_bucket(ip)
    now = time.time()

    if bucket["count"] >= MAX_ATTEMPTS:
        retry_after = int(WINDOW_SECONDS - (now - bucket["window_start"])) + 1
        return False, retry_after

    return True, 0


def record_failed_attempt(ip: str) -> None:
    """Increment the failure counter for this IP."""
    bucket = _get_bucket(ip)
    bucket["count"] += 1


def reset_rate_limit(ip: str) -> None:
    """Reset the counter on successful login."""
    _login_attempts.pop(ip, None)
