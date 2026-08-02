import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from backend.media.tts import generate_tts_audio
from backend.media.meme_generator import generate_meme_image

router = APIRouter(prefix="/api/media", tags=["Media Engine"])

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "christopher"

class MemeRequest(BaseModel):
    top_text: Optional[str] = ""
    bottom_text: Optional[str] = ""
    bg_color: Optional[str] = "#1e1e2e"
    text_color: Optional[str] = "#ffffff"

@router.post("/tts")
async def create_tts(req: TTSRequest):
    try:
        audio_path = await generate_tts_audio(req.text, req.voice or "christopher")
        return FileResponse(audio_path, media_type="audio/mpeg", filename="tts_speech.mp3")
    except Exception as e:
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
        return FileResponse(image_path, media_type="image/png", filename="meme.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meme Error: {str(e)}")

import httpx
import tempfile
import base64
from backend.config import settings

class ImageGenRequest(BaseModel):
    prompt: str
    model: Optional[str] = "stable-diffusion-3.5-large"

@router.post("/image")
async def create_image(req: ImageGenRequest):
    selected_model = req.model or "stable-diffusion-3.5-large"
    
    # Try DigitalOcean Gradient Image Generation API if key is present
    if settings.DO_MODEL_ACCESS_KEY:
        try:
            url = "https://inference.do-ai.run/v1/images/generations"
            headers = {
                "Authorization": f"Bearer {settings.DO_MODEL_ACCESS_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": req.prompt,
                "model": selected_model,
                "n": 1,
                "size": "1024x1024"
            }
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    img_item = data.get("data", [{}])[0]
                    img_url = img_item.get("url")
                    b64_json = img_item.get("b64_json")

                    temp_path = os.path.join(tempfile.gettempdir(), f"do_art_{os.urandom(4).hex()}.png")

                    if img_url:
                        img_res = await client.get(img_url)
                        with open(temp_path, "wb") as f:
                            f.write(img_res.content)
                        return FileResponse(temp_path, media_type="image/png", filename="do_image.png")
                    elif b64_json:
                        with open(temp_path, "wb") as f:
                            f.write(base64.b64decode(b64_json))
                        return FileResponse(temp_path, media_type="image/png", filename="do_image.png")
        except Exception as do_err:
            print(f"[Media Note] DO Image Gen fallback: {do_err}")

    # Local PIL Card Renderer Fallback
    try:
        image_path = generate_meme_image(
            top_text=f"AI ART ({selected_model}):",
            bottom_text=req.prompt[:70],
            bg_color="#0f172a",
            text_color="#38bdf8"
        )
        return FileResponse(image_path, media_type="image/png", filename="ai_image.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image Error: {str(e)}")


