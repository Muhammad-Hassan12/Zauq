from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.memory.db import db_helper

router = APIRouter(prefix="/api/model", tags=["Model Selection"])

class ModelSetRequest(BaseModel):
    channel_id: str
    tier: int
    provider: str
    model_name: Optional[str] = None
    updated_by: Optional[str] = ""

@router.get("/status")
async def get_model_status(channel_id: str):
    selection = await db_helper.get_model_selection(channel_id)
    if not selection:
        # Default Tier 1 Gemini if none configured
        return {
            "channel_id": channel_id,
            "tier": 1,
            "provider": "gemini",
            "model_name": "gemini-2.5-flash",
            "is_default": True
        }
    return selection

from backend.models.router import model_router

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

    provider_lower = req.provider.lower()
    if provider_lower not in valid_providers[req.tier]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider for Tier {req.tier}. Allowed: {valid_providers[req.tier]}"
        )

    # Health check ping for Tier 3 Kaggle tunnel
    if req.tier == 3 or provider_lower == "kaggle":
        kaggle_client = model_router._get_kaggle_client()
        is_online = await kaggle_client.ping()
        if not is_online:
            raise HTTPException(
                status_code=400,
                detail="Tier 3 (Kaggle T4 Tunnel) is currently offline or unreachable. Please wake Kaggle tunnel first."
            )

    # Set default model names if not supplied
    default_models = {
        "gemini": "gemini-2.5-flash",
        "digitalocean": "llama3.3-70b-instruct",
        "ollama": "qwen3.5:4b",
        "kaggle": "qwen3.5-t4"
    }
    model_name = req.model_name or default_models.get(provider_lower, "default")

    result = await db_helper.upsert_model_selection(
        channel_id=req.channel_id,
        tier=req.tier,
        provider=provider_lower,
        model_name=model_name,
        updated_by=req.updated_by or ""
    )
    return {
        "status": "success",
        "data": result
    }

