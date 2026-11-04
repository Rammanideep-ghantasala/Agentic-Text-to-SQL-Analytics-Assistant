import time
from collections import defaultdict, deque
from typing import Deque, DefaultDict

from fastapi import HTTPException, Request, status

from app.config import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: DefaultDict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please wait before making another LLM request.",
            )
        bucket.append(now)


rate_limiter = InMemoryRateLimiter()


def protect_expensive_call(request: Request) -> None:
    settings = get_settings()
    client = request.client.host if request.client else "unknown"
    rate_limiter.check(client, settings.rate_limit_per_minute)
    if not settings.effective_demo_mode and settings.llm_access_token:
        provided = request.headers.get("x-llm-access-token")
        if provided != settings.llm_access_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid LLM access token.")

