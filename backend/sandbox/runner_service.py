"""Isolated HTTP Sandbox Runner Service for Zauq v4.

Runs as a separate isolated microservice that has access to the Docker socket,
decoupling the main Zauq backend from Docker privileges.

Authentication:
Secured via constant-time token comparison against INTERNAL_API_KEY.
"""

from __future__ import annotations
import hmac
import logging
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.config import settings
from backend.sandbox.code_runner import execute_code_docker, get_sandbox_status

logger = logging.getLogger("zauq.sandbox.runner")

app = FastAPI(
    title="Zauq Isolated Sandbox Runner",
    version="4.0.0",
    docs_url=None,  # Disabled for security on internal service
    redoc_url=None,
)


class CodeExecRequest(BaseModel):
    code: str = Field(..., description="Source code to execute in isolated container")
    language: str = Field(default="python", description="Language: python, javascript, or bash")
    timeout: Optional[float] = Field(default=8.0, ge=1.0, le=30.0, description="Max execution time (1-30s)")


def verify_internal_auth(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """Verify internal caller authentication using constant-time comparison."""
    expected_key = getattr(settings, "INTERNAL_API_KEY", "")
    if not expected_key:
        # If no key is configured in dev/testing, allow internal network call
        return

    token = x_internal_token
    if not token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token or not hmac.compare_digest(token, expected_key):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing internal authentication token.",
        )


@app.get("/health")
async def health_check():
    """Liveness check for container orchestrators."""
    return {"status": "ok", "service": "sandbox-runner"}


@app.get("/status")
async def runner_status(auth: None = Depends(verify_internal_auth)):
    """Returns Docker daemon availability and sandbox limits."""
    return await get_sandbox_status()


@app.post("/execute")
async def runner_execute(
    req: CodeExecRequest,
    auth: None = Depends(verify_internal_auth),
):
    """Execute code in a hardened Docker container."""
    result = await execute_code_docker(
        code=req.code,
        language=req.language,
        timeout=req.timeout,
    )
    return result
