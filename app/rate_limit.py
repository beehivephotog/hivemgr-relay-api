"""Minimal in-process rate limiter. Single free-tier instance, no Redis needed for v1:
defense-in-depth on the one public POST endpoint (the token itself is already 256 bits
of entropy, so this guards against abuse/mistakes more than realistic brute force)."""
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)
WINDOW_SECONDS = 60
MAX_REQUESTS = 10


def rate_limit_ip(request: Request, max_requests: int = MAX_REQUESTS, window: int = WINDOW_SECONDS) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _lock:
        hits = [t for t in _hits[ip] if now - t < window]
        if len(hits) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")
        hits.append(now)
        _hits[ip] = hits
