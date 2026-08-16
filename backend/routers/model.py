from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.memory.db import db_helper
from backend.models.router import model_router

router = APIRouter(prefix="/api/model", tags=["Model Selection"])

class ModelSetRequest(BaseModel):
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    scope: Optional[str] = "channel"  # 'channel' or 'server'
    tier: int
    provider: str
    model_name: Optional[str] = None
    updated_by: Optional[str] = ""

def normalize_provider(raw_provider: str) -> str:
    p = raw_provider.lower().strip()
    if p in ["google", "gemini", "google ai studio", "gemma"]:
        return "gemini"
    if p in ["do", "digitalocean", "gradient"]:
        return "digitalocean"
    if p in ["ollama", "local"]:
        return "ollama"
    if p in ["kaggle", "batch gpu"]:
        return "kaggle"
    return p

@router.get("/status")
async def get_model_status(channel_id: str, guild_id: Optional[str] = None):
    # 1. Check Channel Override
    selection = await db_helper.get_model_selection(channel_id)
    if selection:
        return {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "tier": selection.get("tier", 1),
            "provider": selection.get("provider", "gemini"),
            "model_name": selection.get("model_name", "gemini-2.5-flash"),
            "updated_by": selection.get("updated_by", "Admin"),
            "scope": "channel",
            "is_channel_override": True,
            "is_default": False
        }

    # 2. Check Server Community Default
    if guild_id and guild_id != "dm":
        guild_cfg = await db_helper.get_guild_config(guild_id)
        if guild_cfg and guild_cfg.get("default_provider"):
            return {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "tier": guild_cfg.get("default_tier", 1),
                "provider": guild_cfg.get("default_provider", "gemini"),
                "model_name": guild_cfg.get("default_model_name", "gemini-2.5-flash"),
                "updated_by": "Server Default",
                "scope": "server",
                "is_server_default": True,
                "is_default": False
            }

    # 3. System Global Fallback (Tier 1 Google Gemini)
    return {
        "channel_id": channel_id,
        "guild_id": guild_id,
        "tier": 1,
        "provider": "gemini",
        "model_name": "gemini-2.5-flash",
        "updated_by": "System Default",
        "scope": "system",
        "is_system_fallback": True,
        "is_default": True
    }

@router.get("/gemini-models")
async def list_gemini_models():
    """Returns available models from Google AI Studio (Gemini & Gemma families)."""
    return {
        "gemini": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite"
        ],
        "gemma": [
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it"
        ]
    }

@router.get("/do-models")
async def list_do_models():
    """Returns available models from DigitalOcean Gradient Serverless Inference."""
    return {
        "models": [
            "kimi-k3",
            "glm-5.1",
            "glm-5.2",
            "deepseek-v4-pro",
            "deepseek-4-flash",
            "qwen3.5-397b-a17b",
            "llama3.3-70b-instruct"
        ]
    }

@router.post("/set")
async def set_model_selection(req: ModelSetRequest):
    valid_providers = {
        1: ["gemini", "digitalocean"],
        2: ["ollama"],
        3: ["kaggle"]
    }
    if req.tier not in valid_providers:
        raise HTTPException(status_code=400, detail="Invalid tier. Choose 1, 2, or 3.")

    provider_clean = normalize_provider(req.provider)
    if provider_clean not in valid_providers[req.tier]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider for Tier {req.tier}. Allowed: {valid_providers[req.tier]} (Note: Google/Gemini are in Tier 1)."
        )

    # Health check ping for Tier 3 Kaggle tunnel
    if req.tier == 3 or provider_clean == "kaggle":
        kaggle_client = model_router._get_kaggle_client()
        is_online = await kaggle_client.ping()
        if not is_online:
            raise HTTPException(
                status_code=400,
                detail="Tier 3 (Kaggle T4 Tunnel) is currently offline or unreachable. Please wake Kaggle tunnel first."
            )

    # Default model names if not supplied
    default_models = {
        "gemini": "gemini-2.5-flash",
        "digitalocean": "llama3.3-70b-instruct",
        "ollama": "qwen3.5:4b",
        "kaggle": "qwen3.5-t4"
    }
    model_name = req.model_name or default_models.get(provider_clean, "default")

    scope = (req.scope or "channel").lower()

    if scope in ["server", "community", "guild"] and req.guild_id and req.guild_id != "dm":
        # Save as server-wide community default
        result = await db_helper.upsert_guild_config(
            guild_id=req.guild_id,
            default_tier=req.tier,
            default_provider=provider_clean,
            default_model_name=model_name
        )
        return {
            "status": "success",
            "scope": "server",
            "data": {
                "guild_id": req.guild_id,
                "tier": req.tier,
                "provider": provider_clean,
                "model_name": model_name,
                "updated_by": req.updated_by or "Admin"
            }
        }
    else:
        # Save as channel-specific override
        if not req.channel_id:
            raise HTTPException(status_code=400, detail="channel_id is required for channel-scoped configuration.")
        result = await db_helper.upsert_model_selection(
            channel_id=req.channel_id,
            tier=req.tier,
            provider=provider_clean,
            model_name=model_name,
            updated_by=req.updated_by or "Admin"
        )
        return {
            "status": "success",
            "scope": "channel",
            "data": result
        }

@router.post("/reset")
async def reset_model_selection(channel_id: str):
    """Deletes a channel model override so it inherits the community server default."""
    success = await db_helper.delete_model_selection(channel_id)
    return {
        "status": "success",
        "channel_id": channel_id,
        "cleared": success,
        "detail": "Channel model override cleared. Channel will now inherit the community server default."
    }
