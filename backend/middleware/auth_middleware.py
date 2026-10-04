import hmac
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.config import settings

logger = logging.getLogger("zauq.auth")

# Endpoints that do NOT require authentication
_PUBLIC_PATHS = {"/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Internal API Key authentication middleware.
    Every request must include the X-Zauq-Token header matching INTERNAL_API_KEY.
    Public paths (/health) are exempt. Missing credentials deny access unless
    DEVELOPMENT_MODE is explicitly enabled.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Always allow health check
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        if not settings.INTERNAL_API_KEY:
            if settings.DEVELOPMENT_MODE:
                return await call_next(request)
            return JSONResponse(status_code=503, content={'detail':'Internal authentication is not configured.'})

        token = request.headers.get("X-Zauq-Token", "")
        if not token or not hmac.compare_digest(token, settings.INTERNAL_API_KEY):
            logger.warning(
                f"Unauthorized request to {request.url.path} "
                f"from {request.client.host if request.client else 'unknown'}"
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing X-Zauq-Token header."}
            )

        return await call_next(request)
