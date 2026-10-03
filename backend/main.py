import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.config import settings
from backend.version import ZAUQ_VERSION
from backend.logging_config import setup_logging
from backend.utils.temp_manager import temp_file_manager
from backend.memory.memory_worker import start_memory_decay_worker
from backend.middleware.rate_limiter import RateLimitMiddleware
from backend.middleware.auth_middleware import AuthMiddleware
from backend.routers import (
    chat, model, sandbox, lore, github, media, games, admin,
    context, xp_router, reminders, moderation
)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: launch background workers. Shutdown: cancel them cleanly."""
    cleanup_task = asyncio.create_task(temp_file_manager.cleanup_loop())
    memory_decay_task = asyncio.create_task(start_memory_decay_worker())

    # ── v4 Phase 6: MCP Client Lifecycle ──────────────────────────────────────
    if settings.MCP_ENABLED:
        from backend.mcp_client.manager import mcp_manager
        await mcp_manager.start()

    yield

    # Clean up MCP connections
    if settings.MCP_ENABLED:
        from backend.mcp_client.manager import mcp_manager
        await mcp_manager.stop()

    cleanup_task.cancel()
    memory_decay_task.cancel()
    for task in [cleanup_task, memory_decay_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Zauq Backend API Engine",
    description="AgenticEra Decoupled Hybrid AI Engine for Zauq Discord Bot",
    version=ZAUQ_VERSION,
    lifespan=lifespan
)

# Auth middleware first (outermost), then rate limiter
app.add_middleware(RateLimitMiddleware, guild_limit=30, user_limit=10)
app.add_middleware(AuthMiddleware)

from backend.mcp_client.health import router as mcp_router

app.include_router(chat.router)
app.include_router(model.router)
app.include_router(sandbox.router)
app.include_router(lore.router)
app.include_router(github.router)
app.include_router(media.router)
app.include_router(games.router)
app.include_router(admin.router)
app.include_router(context.router)
app.include_router(xp_router.router)
app.include_router(reminders.router)
app.include_router(moderation.router)
app.include_router(mcp_router)

from backend.routers.actions import router as actions_router
app.include_router(actions_router)

from backend.routers.agent import router as agent_router
app.include_router(agent_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Zauq Backend",
        "version": ZAUQ_VERSION
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
