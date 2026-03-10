import redis.asyncio as redis
import os
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client: Optional[redis.Redis] = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    # Malformed URL or init failure: app can run without Redis (e.g. rate limiting disabled)
    pass

async def get_redis() -> Optional[redis.Redis]:
    return redis_client