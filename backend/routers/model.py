from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.memory.db import db_helper
from backend.models.router import model_router

from backend.models.catalog import (
    normalize_provider_id,
    validate_provider_tier,
    validate_provider_credentials,
    get_provider,
    list_providers,
    get_models_for_provider,
    VALID_TIER_PROVIDERS,
    PROVIDERS,
)

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
    return normalize_provider_id(raw_provider)

@router.get("/providers")
async def get_all_providers():
    """Returns all registered AI providers, tiers, and capabilities from the central catalog."""
    return {"providers": [p.__dict__ for p in list_providers()]}

@router.get("/catalog/{provider}")
async def get_provider_catalog(provider: str):
    """Returns available models for the specified provider."""
    models = get_models_for_provider(provider)
    if not models:
        clean_id = normalize_provider_id(provider)
        if clean_id not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'.")
    return {"provider": normalize_provider_id(provider), "models": models}

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
        "models": get_models_for_provider("digitalocean")
    }

@router.post("/set")
async def set_model_selection(req: ModelSetRequest):
    if req.tier not in VALID_TIER_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid tier. Choose 1, 2, or 3.")

    provider_clean = normalize_provider_id(req.provider)
    if not validate_provider_tier(provider_clean, req.tier):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider for Tier {req.tier}. Allowed: {VALID_TIER_PROVIDERS[req.tier]}"
        )

    # Validate provider credentials before saving
    is_valid, cred_err = validate_provider_credentials(provider_clean)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Credential validation failed: {cred_err}"
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

    # Default model resolution from central catalog
    prov_spec = get_provider(provider_clean)
    default_model = prov_spec.default_model if prov_spec else "gemini-2.5-flash"
    model_name = req.model_name or default_model

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

@router.get("/info")
async def get_full_system_info(channel_id: str, guild_id: Optional[str] = None):
    """
    Returns complete live specifications, active model tier, mode, and capabilities.
    """
    # 1. Resolve Model Selection & Scope
    status_data = await get_model_status(channel_id, guild_id)
    tier = status_data.get("tier", 1)
    provider = status_data.get("provider", "gemini")
    model_name = status_data.get("model_name", "gemini-2.5-flash")
    scope = status_data.get("scope", "system")

    # 2. Resolve Operating Mode & Sandbox Execution
    channel_profile = await db_helper.get_channel_profile(channel_id)
    thinking_enabled = bool(channel_profile.get("thinking_enabled", False)) if channel_profile else False
    if channel_profile:
        mode = channel_profile.get("operating_mode", "hangout")
        temp = float(channel_profile.get("temperature", 0.2 if mode == "dev" else 0.75))
        allow_code_exec = channel_profile.get("allow_code_exec", mode == "dev")
    else:
        guild_cfg = await db_helper.get_guild_config(guild_id) if (guild_id and guild_id != "dm") else None
        if guild_cfg and guild_cfg.get("default_mode"):
            mode = guild_cfg.get("default_mode", "hangout")
            temp = 0.2 if mode == "dev" else 0.75
            allow_code_exec = (mode == "dev")
        else:
            mode = "hangout"
            temp = 0.75
            allow_code_exec = False

    return {
        "engine": {
            "name": "Zauq (ذوق)",
            "version": "3.2.5",
            "creator": "Syed Muhammad Hassan / AgenticEra Systems",
            "license": "Apache License 2.0",
            "backend_port": 8002,
            "status": "online"
        },
        "model": {
            "tier": tier,
            "provider": provider,
            "model_name": model_name,
            "scope": scope,
            "is_channel_override": status_data.get("is_channel_override", False),
            "is_server_default": status_data.get("is_server_default", False),
            "updated_by": status_data.get("updated_by", "System")
        },
        "persona": {
            "mode": mode,
            "temperature": temp,
            "allow_code_exec": allow_code_exec,
            "thinking_enabled": thinking_enabled
        },
        "limits": {
            "input_tokens_max": 30000,
            "input_chars_max": 120000,
            "output_tokens_max": 65536,
            "history_window": 8,
            "sandbox_timeout_s": 5.0,
            "sandbox_memory": "256m",
            "sandbox_cpus": "0.5"
        },
        "capabilities": {
            "web_search": "Deep Web Roaming + Google Grounding + DuckDuckGo",
            "voice_tts": "Microsoft Edge Neural TTS (19 Voices, 8 Languages)",
            "image_generation": "Gemini Flash Image (Free) / DigitalOcean SD3.5",
            "memory": "L1 (8 msgs) · L2 (768-dim vector facts + decay) · L3 (pgvector lore)",
            "ssrf_protection": "Active (DNS Filter & Private IP Blocking)",
            "multimodal": "Voice Notes (Urdu/English/etc), PDFs, DOCX, Code, Images"
        }
    }
