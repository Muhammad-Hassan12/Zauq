import logging
import httpx
from typing import Optional
from backend.config import settings

logger = logging.getLogger("zauq.audio_transcriber")

class AudioTranscriber:
    """
    Multilingual Audio Transcriber using Gemini Flash.
    Provides lossless speech-to-text for Urdu, Hindi, Arabic, English, and all global languages
    when routing to text-only models (DigitalOcean, Ollama, Kaggle).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY

    async def transcribe(self, audio_bytes_b64: str, mime_type: str = "audio/ogg") -> str:
        """
        Transcribes audio bytes into exact spoken text in the original language.
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set for audio transcription.")
            return "[Audio file provided - API key missing for transcription]"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": audio_bytes_b64
                            }
                        },
                        {
                            "text": (
                                "Transcribe the exact spoken words in this audio verbatim. "
                                "Preserve the original spoken language (Urdu, Hindi, English, Arabic, etc.) and original script/alphabet. "
                                "Do NOT translate, do NOT summarize, do NOT output explanations. Output ONLY the raw spoken text."
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    transcript = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return transcript
                else:
                    logger.error(f"Audio transcription failed ({res.status_code}): {res.text}")
                    return f"[Audio transcription error: HTTP {res.status_code}]"
        except Exception as e:
            logger.error(f"Audio transcription exception: {e}")
            return f"[Audio transcription failed: {str(e)}]"

audio_transcriber = AudioTranscriber()
