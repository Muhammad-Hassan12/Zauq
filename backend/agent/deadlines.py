import asyncio
from functools import wraps
from backend.config import settings


def bounded_runtime(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        deep = kwargs.get('deep_search', False)
        configured = settings.AGENT_DEEP_RESEARCH_TIMEOUT_SECONDS if deep else settings.AGENT_TOTAL_TIMEOUT_SECONDS
        async with asyncio.timeout(max(.01, min(configured, 180 if deep else 90))):
            return await function(*args, **kwargs)
    return wrapped
