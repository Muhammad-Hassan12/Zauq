import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.config import settings
from backend.logging_config import setup_logging
from backend.utils.temp_manager import temp_file_manager
from backend.middleware.rate_limiter import RateLimitMiddleware
from backend.middleware.auth_middleware import AuthMiddleware
from backend.routers import (
    chat, model, sandbox, lore, github, media, games, admin,
    context, xp_router, reminders, moderation
)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: launch background cleanup worker. Shutdown: cancel it cleanly."""
    cleanup_task = asyncio.create_task(temp_file_manager.cleanup_loop())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Zauq Backend API Engine",
    description="AgenticEra Decoupled Hybrid AI Engine for Zauq Discord Bot",
    version="3.0.0",
    lifespan=lifespan
)

# Auth middleware first (outermost), then rate limiter
app.add_middleware(RateLimitMiddleware, guild_limit=30, user_limit=10)
app.add_middleware(AuthMiddleware)

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


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Zauq Backend",
        "version": "3.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
