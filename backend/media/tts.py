import os
import tempfile
import edge_tts
from typing import List, Dict

VOICE_PRESETS = {
    # English
    "christopher": "en-US-ChristopherNeural",
    "ava": "en-US-AvaNeural",
    "guy": "en-US-GuyNeural",
    "sonia": "en-GB-SoniaNeural",
    "brian": "en-GB-RyanNeural",
    # Urdu
    "asad": "ur-PK-AsadNeural",
    "uzma": "ur-PK-UzmaNeural",
    # Hindi
    "madhur": "hi-IN-MadhurNeural",
    "swara": "hi-IN-SwaraNeural",
    # Arabic
    "hamed": "ar-SA-HamedNeural",
    "zariyah": "ar-SA-ZariyahNeural",
    # Spanish
    "alvaro": "es-ES-AlvaroNeural",
    "elvira": "es-ES-ElviraNeural",
    # French
    "henri": "fr-FR-HenriNeural",
    "denise": "fr-FR-DeniseNeural",
    # German
    "conrad": "de-DE-ConradNeural",
    "katja": "de-DE-KatjaNeural",
    # Japanese
    "keita": "ja-JP-KeitaNeural",
    "nanami": "ja-JP-NanamiNeural"
}

async def generate_tts_audio(text: str, voice: str = "en-US-ChristopherNeural") -> str:
    """
    Synthesizes speech from text using Microsoft Edge TTS (free cloud neural synthesis).
    Saves and returns path to generated .mp3 file.
    """
    selected_voice = VOICE_PRESETS.get(voice.lower(), voice)
    communicate = edge_tts.Communicate(text, selected_voice)

    temp_dir = tempfile.gettempdir()
    output_filename = f"zauq_tts_{os.urandom(6).hex()}.mp3"
    output_path = os.path.join(temp_dir, output_filename)

    await communicate.save(output_path)
    return output_path
