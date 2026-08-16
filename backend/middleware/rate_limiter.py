import time
import json
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Per-endpoint rate limit overrides (guild_limit, user_limit)
_ENDPOINT_LIMITS = {
    "/api/sandbox/exec": (10, 5),
    "/api/media/image": (10, 3),
    "/api/media/tts": (15, 5),
    "/api/media/meme": (15, 5),
    "/api/moderation/check": (20, 10),
}
_DEFAULT_LIMITS = (30, 15)
_CHAT_LIMITS = (30, 10)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, guild_limit: int = 30, user_limit: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.guild_limit = guild_limit
        self.user_limit = user_limit
        self.window_seconds = window_seconds
        self.guild_requests = defaultdict(list)
        self.user_requests = defaultdict(list)
        self.ip_requests = defaultdict(list)
        self.last_cleanup = time.time()

    def _cleanup_stale_keys(self, now: float):
        if now - self.last_cleanup > 300:
            for store in [self.guild_requests, self.user_requests, self.ip_requests]:
                for key in list(store.keys()):
                    store[key] = [t for t in store[key] if now - t < self.window_seconds]
                    if not store[key]:
                        del store[key]
            self.last_cleanup = now

    def _is_rate_limited(self, requests_dict: dict, key: str, limit: int) -> bool:
        if not key:
            return False
        now = time.time()
        self._cleanup_stale_keys(now)
        requests_dict[key] = [t for t in requests_dict[key] if now - t < self.window_seconds]
        if len(requests_dict[key]) >= limit:
            return True
        requests_dict[key].append(now)
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only rate-limit POST requests
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path

        # Determine limits for this endpoint
        if path.startswith("/api/chat"):
            guild_limit, user_limit = _CHAT_LIMITS
        else:
            guild_limit, user_limit = _ENDPOINT_LIMITS.get(path, _DEFAULT_LIMITS)

        # Get client IP for fallback
        client_ip = request.client.host if request.client else "unknown"

        guild_id = None
        user_id = None

        try:
            body_bytes = await request.body()

            # Re-construct request so body stream is not consumed
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request = Request(request.scope, receive=receive)

            if body_bytes:
                body = json.loads(body_bytes.decode("utf-8"))
                guild_id = body.get("guild_id")
                user_id = body.get("user_id")

        except Exception:
            # Body parse failed — fall back to IP-based rate limiting
            if self._is_rate_limited(self.ip_requests, client_ip, user_limit):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."}
                )
            return await call_next(request)

        # Guild-level check
        if guild_id and self._is_rate_limited(self.guild_requests, guild_id, guild_limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"Guild rate limit exceeded (max {guild_limit} requests/min). Please try again shortly."}
            )

        # User-level check
        if user_id and self._is_rate_limited(self.user_requests, user_id, user_limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"User rate limit exceeded (max {user_limit} requests/min). Please slow down."}
            )

        # IP-level fallback check (when no user_id extracted)
        if not user_id:
            if self._is_rate_limited(self.ip_requests, client_ip, user_limit):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."}
                )

        return await call_next(request)
