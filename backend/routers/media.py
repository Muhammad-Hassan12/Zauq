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

class ImageGenRequest(BaseModel):
    prompt: str

@router.post("/image")
async def create_image(req: ImageGenRequest):
    try:
        # Generate card image visualization for prompt
        image_path = generate_meme_image(
            top_text=f"AI ART: {req.prompt[:30]}",
            bottom_text=req.prompt[30:80] if len(req.prompt) > 30 else "",
            bg_color="#0f172a",
            text_color="#38bdf8"
        )
        return FileResponse(image_path, media_type="image/png", filename="ai_image.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image Error: {str(e)}")

