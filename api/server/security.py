from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import requests

from server.config import Config
from utils.logger_handler import logger


class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - max(window_seconds, 1)
        with self._lock:
            q = self._events[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max(limit, 1):
                retry_after = int(max(1, q[0] + window_seconds - now))
                return False, retry_after
            q.append(now)
            return True, 0


_LIMITER = _SlidingWindowLimiter()


def enforce_rate_limit(endpoint: str, remote_ip: str) -> Tuple[bool, int, dict]:
    if not Config.RATE_LIMIT_ENFORCE:
        return True, 200, {}

    ip = (remote_ip or "unknown").strip() or "unknown"
    key = f"{endpoint}:{ip}"
    allowed, retry_after = _LIMITER.allow(
        key=key,
        limit=Config.RATE_LIMIT_REQUESTS,
        window_seconds=Config.RATE_LIMIT_WINDOW_SECONDS,
    )
    if allowed:
        return True, 200, {}

    return False, 429, {
        "error": "rate_limited",
        "message": "Too many requests. Please retry later.",
        "retry_after": retry_after,
    }


def verify_turnstile_token(token: str, remote_ip: str) -> Tuple[bool, str]:
    if not Config.TURNSTILE_ENFORCE:
        return True, ""

    token = (token or "").strip()
    if not token:
        return False, "missing_turnstile_token"

    secret = (Config.TURNSTILE_SECRET_KEY or "").strip()
    if not secret:
        logger.error("TURNSTILE_ENFORCE=true but TURNSTILE_SECRET_KEY is empty.")
        return False, "turnstile_not_configured"

    payload = {
        "secret": secret,
        "response": token,
    }
    ip = (remote_ip or "").strip()
    if ip:
        payload["remoteip"] = ip

    try:
        resp = requests.post(Config.TURNSTILE_VERIFY_URL, data=payload, timeout=6)
        body = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
    except Exception as e:
        logger.warning("Turnstile verify request failed: %s", e)
        return False, "turnstile_verify_failed"

    if not isinstance(body, dict) or not body.get("success"):
        codes = body.get("error-codes") if isinstance(body, dict) else []
        if isinstance(codes, list):
            code_text = ",".join(str(c) for c in codes[:3])
        else:
            code_text = str(codes or "")
        return False, f"turnstile_rejected:{code_text}".strip(":")

    return True, ""


def enforce_high_cost_guard(endpoint: str, token: str, remote_ip: str) -> Tuple[bool, int, dict]:
    allowed, status, rate_error = enforce_rate_limit(endpoint=endpoint, remote_ip=remote_ip)
    if not allowed:
        return False, status, rate_error

    ok, reason = verify_turnstile_token(token=token, remote_ip=remote_ip)
    if not ok:
        return False, 403, {
            "error": "turnstile_failed",
            "message": "Turnstile verification failed.",
            "reason": reason,
        }

    return True, 200, {}

