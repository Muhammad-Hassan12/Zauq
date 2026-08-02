import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.routers import chat, model, sandbox, lore, github, media, games, admin
from backend.middleware.rate_limiter import RateLimitMiddleware

app = FastAPI(
    title="Zauq Backend API",
    description="AgenticEra Hybrid AI Engine for Zauq Discord Bot",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, guild_limit=30, user_limit=10)

app.include_router(chat.router)
app.include_router(model.router)
app.include_router(sandbox.router)
app.include_router(lore.router)
app.include_router(github.router)
app.include_router(media.router)
app.include_router(games.router)
app.include_router(admin.router)



@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Zauq Backend",
        "version": "2.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
