import os
import httpx
import tempfile
import base64
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from backend.config import settings
from backend.media.tts import generate_tts_audio
from backend.media.meme_generator import generate_meme_image
from backend.media.gemini_image import gemini_image_client
from backend.utils.temp_manager import temp_file_manager

logger = logging.getLogger("zauq.media")

router = APIRouter(prefix="/api/media", tags=["Media Engine"])

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "christopher"

class MemeRequest(BaseModel):
    top_text: Optional[str] = ""
    bottom_text: Optional[str] = ""
    bg_color: Optional[str] = "#1e1e2e"
    text_color: Optional[str] = "#ffffff"

class ImageGenRequest(BaseModel):
    prompt: str
    model: Optional[str] = "gemini-3.1-flash-image"

@router.post("/tts")
async def create_tts(req: TTSRequest):
    try:
        audio_path = await generate_tts_audio(req.text, req.voice or "christopher")
        temp_file_manager.register(audio_path)
        return FileResponse(audio_path, media_type="audio/mpeg", filename="tts_speech.mp3")
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS Error: {str(e)}")

@router.post("/meme")
async def create_meme(req: MemeRequest):
    try:
        image_path = generate_meme_image(
            top_text=req.top_text or "",
            bottom_text=req.bottom_text or "",
            bg_color=req.bg_color or "#1e1e2e",
            text_color=req.text_color or "#ffffff"
        )
        temp_file_manager.register(image_path)
        return FileResponse(image_path, media_type="image/png", filename="meme.png")
    except Exception as e:
        logger.error(f"Meme generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Meme Error: {str(e)}")

@router.post("/image")
async def create_image(req: ImageGenRequest):
    selected_model = (req.model or "gemini-3.1-flash-image").lower()

    # Route 1: Gemini Native Image Generation (Free, Primary)
    if "gemini" in selected_model or "imagen" in selected_model or selected_model == "default":
        if not settings.GEMINI_API_KEY:
            raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured for free AI image generation.")
        try:
            target_model = "gemini-3.1-flash-image" if "gemini" in selected_model else selected_model
            img_bytes = await gemini_image_client.generate_image(req.prompt, model_name=target_model)
            temp_path = os.path.join(tempfile.gettempdir(), f"gemini_art_{os.urandom(4).hex()}.png")
            with open(temp_path, "wb") as f:
                f.write(img_bytes)
            temp_file_manager.register(temp_path)
            return FileResponse(temp_path, media_type="image/png", filename="zauq_ai_art.png")
        except Exception as gem_err:
            logger.error(f"Gemini image generation failed: {gem_err}")
            raise HTTPException(status_code=502, detail=f"Gemini Image Gen Error: {str(gem_err)}")

    # Route 2: DigitalOcean Gradient Image Generation
    if "stable-diffusion" in selected_model or "ideogram" in selected_model:
        if not settings.DO_MODEL_ACCESS_KEY:
            raise HTTPException(status_code=400, detail="DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
        try:
            url = "https://inference.do-ai.run/v1/images/generations"
            headers = {
                "Authorization": f"Bearer {settings.DO_MODEL_ACCESS_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": req.prompt,
                "model": req.model,
                "n": 1,
                "size": "1024x1024"
            }
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    logger.error(f"DO Image Gen API Error ({res.status_code}): {res.text}")
                    raise HTTPException(status_code=502, detail=f"DigitalOcean API Error ({res.status_code}): {res.text}")

                data = res.json()
                img_item = data.get("data", [{}])[0]
                img_url = img_item.get("url")
                b64_json = img_item.get("b64_json")

                temp_path = os.path.join(tempfile.gettempdir(), f"do_art_{os.urandom(4).hex()}.png")

                if img_url:
                    img_res = await client.get(img_url)
                    with open(temp_path, "wb") as f:
                        f.write(img_res.content)
                    temp_file_manager.register(temp_path)
                    return FileResponse(temp_path, media_type="image/png", filename="do_image.png")
                elif b64_json:
                    with open(temp_path, "wb") as f:
                        f.write(base64.b64decode(b64_json))
                    temp_file_manager.register(temp_path)
                    return FileResponse(temp_path, media_type="image/png", filename="do_image.png")
                else:
                    raise HTTPException(status_code=500, detail="Invalid response structure from DigitalOcean Image API.")

        except HTTPException:
            raise
        except Exception as do_err:
            logger.error(f"DO Image Gen exception: {do_err}")
            raise HTTPException(status_code=502, detail=f"DO Image Gen Error: {str(do_err)}")

    # Route 3: Fallback Offline Card
    try:
        image_path = generate_meme_image(
            top_text=f"AI ART ({req.model}):",
            bottom_text=req.prompt[:70],
            bg_color="#0f172a",
            text_color="#38bdf8"
        )
        temp_file_manager.register(image_path)
        return FileResponse(image_path, media_type="image/png", filename="ai_image.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image Error: {str(e)}")
