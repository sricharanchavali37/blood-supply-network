from fastapi import HTTPException, status, Request
from app.core.redis import redis_client
from app.core.config import settings
from typing import Optional

async def check_rate_limit(request: Request, identifier: Optional[str] = None) -> None:
    if redis_client is None:
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
                detail="Too many requests. Please try again later."
            )
        await redis_client.incr(key)
    except HTTPException:
        raise
    except Exception:
        pass