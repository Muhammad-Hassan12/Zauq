import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, guild_limit: int = 30, user_limit: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.guild_limit = guild_limit
        self.user_limit = user_limit
        self.window_seconds = window_seconds
        self.guild_requests = defaultdict(list)
        self.user_requests = defaultdict(list)

    def _is_rate_limited(self, requests_dict: dict, key: str, limit: int) -> bool:
        if not key:
            return False
        now = time.time()
        # Filter out timestamps outside window
        requests_dict[key] = [t for t in requests_dict[key] if now - t < self.window_seconds]
        if len(requests_dict[key]) >= limit:
            return True
        requests_dict[key].append(now)
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only rate-limit POST requests to /api/chat
        if request.method == "POST" and request.url.path.startswith("/api/chat"):
            try:
                body = await request.json()
                guild_id = body.get("guild_id")
                user_id = body.get("user_id")

                if self._is_rate_limited(self.guild_requests, guild_id, self.guild_limit):
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Guild rate limit exceeded (max 30 requests/min). Please try again shortly."}
                    )

                if self._is_rate_limited(self.user_requests, user_id, self.user_limit):
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "User rate limit exceeded (max 10 requests/min). Please slow down."}
                    )

            except Exception:
                pass  # If body parsing fails, proceed to endpoint handler

        return await call_next(request)
