# app/core/rate_limit.py

from fastapi import HTTPException, status, Request
from app.core.redis import redis_client
from app.core.config import settings
from typing import Optional

_redis_available = True


async def check_rate_limit(request: Request, identifier: Optional[str] = None) -> None:
    """
    Enforce per-identifier sliding-window rate limiting via Redis.

    BUG FIXED: The previous version used a bare `except Exception` which silently
    caught and discarded `HTTPException(429)` before it could be propagated to the
    client. Now we re-raise `HTTPException` explicitly so rate-limit responses are
    delivered correctly, while all other Redis errors disable rate limiting
    gracefully.
    """
    global _redis_available
    if not _redis_available or redis_client is None:
        return

    if identifier is None:
        identifier = request.client.host

    key = f"rate_limit:{identifier}"

    try:
        current = await redis_client.get(key)

        if current is None:
            await redis_client.setex(key, settings.RATE_LIMIT_WINDOW, 1)
            return

        current_count = int(current)

        if current_count >= settings.RATE_LIMIT_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

        await redis_client.incr(key)

    except HTTPException:
        # Always re-raise HTTP exceptions (e.g. 429) — never swallow them.
        raise
    except Exception:
        # Redis failure: degrade gracefully by disabling rate limiting.
        _redis_available = False
