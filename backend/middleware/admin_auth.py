"""Admin-endpoint authorization dependency for Zauq v4.

Provides a FastAPI dependency that enforces a second-layer token check for
privileged /api/admin/* operations, independent of the general INTERNAL_API_KEY
used by the bot for normal operations.

If ADMIN_API_KEY is not set separately, the dependency falls back to
INTERNAL_API_KEY so existing single-key deployments keep working without
any configuration change.
"""
import hmac
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger("zauq.admin.auth")


async def require_admin_token(request: Request) -> None:
    """FastAPI dependency. Raises HTTP 403 when the caller is not presenting
    a valid admin token in the X-Zauq-Admin-Token header.

    Backward-compatibility: When ADMIN_API_KEY is not configured, the check
    falls through to INTERNAL_API_KEY so existing setups are unaffected.
    """
    from backend.config import settings

    # Determine effective admin secret
    effective_key = settings.ADMIN_API_KEY or settings.INTERNAL_API_KEY
    if not effective_key:
        # No keys configured at all — only allowed in DEVELOPMENT_MODE
        if settings.DEVELOPMENT_MODE:
            return
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured."
        )

    # Accept either header; prefer the dedicated one when present
    token = (
        request.headers.get("X-Zauq-Admin-Token")
        or request.headers.get("X-Zauq-Token", "")
    )
    if not token or not hmac.compare_digest(token, effective_key):
        logger.warning(
            "Unauthorized admin request to %s from %s",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Valid X-Zauq-Admin-Token required for admin operations."
        )
