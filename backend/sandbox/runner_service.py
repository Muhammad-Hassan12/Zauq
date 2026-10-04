"""Isolated HTTP Sandbox Runner Service for Zauq v4.

Runs as a separate isolated microservice that has access to the Docker socket,
decoupling the main Zauq backend from Docker privileges.

Authentication:
Secured via constant-time token comparison against INTERNAL_API_KEY.
"""

from __future__ import annotations
import hmac
import logging
import asyncio
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from backend.config import settings
from backend.version import ZAUQ_VERSION
from backend.sandbox.code_runner import execute_code_docker, get_sandbox_status

logger = logging.getLogger("zauq.sandbox.runner")

app = FastAPI(
    title="Zauq Isolated Sandbox Runner",
    version=ZAUQ_VERSION,
    docs_url=None,  # Disabled for security on internal service
    redoc_url=None,
)


class CodeExecRequest(BaseModel):
    code: str = Field(..., max_length=50000, description="Source code to execute in isolated container")
    language: str = Field(default="python", description="Language: python, javascript, or bash")
    timeout: Optional[float] = Field(default=8.0, ge=1.0, le=30.0, description="Max execution time (1-30s)")


def verify_internal_auth(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """Verify internal caller authentication using constant-time comparison."""
    expected_key = getattr(settings, "INTERNAL_API_KEY", "")
    if not expected_key:
        if settings.DEVELOPMENT_MODE:
            return
        raise HTTPException(status_code=503, detail='Internal authentication is not configured.')

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
    request: Request,
    auth: None = Depends(verify_internal_auth),
):
    """Execute code in a hardened Docker container."""
    task = asyncio.create_task(execute_code_docker(
        code=req.code,
        language=req.language,
        timeout=req.timeout,
    ))
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise HTTPException(status_code=499, detail='Caller disconnected')
            await asyncio.wait({task}, timeout=0.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
