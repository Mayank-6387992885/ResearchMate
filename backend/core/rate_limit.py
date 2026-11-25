import time
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding-window rate limiter per client IP."""

    def __init__(self, app, max_requests_per_minute: int = settings.rate_limit_per_minute):
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if self.max_requests <= 0 or request.url.path in ("/", "/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0
        bucket = self._hits[client_ip]
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": "Too many requests. Please slow down.",
                    "status_code": 429,
                },
            )

        bucket.append(now)
        return await call_next(request)
