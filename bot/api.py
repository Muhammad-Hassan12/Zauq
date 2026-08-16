"""
Shared HTTP client helper for all bot → backend API calls.
Centralises the base URL and auth header in one place.
"""
import httpx
from backend.config import settings

BACKEND_URL = f"http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}"


def api_headers() -> dict:
    """Returns the required internal API auth header."""
    return {"X-Zauq-Token": settings.INTERNAL_API_KEY} if settings.INTERNAL_API_KEY else {}


def api_client(timeout: float = 10.0) -> httpx.AsyncClient:
    """Returns a pre-configured AsyncClient with auth headers set."""
    return httpx.AsyncClient(timeout=timeout, headers=api_headers())
