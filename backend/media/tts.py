import os
import tempfile
import edge_tts
from typing import List, Dict

VOICE_PRESETS = {
    "christopher": "en-US-ChristopherNeural",
    "ava": "en-US-AvaNeural",
    "guy": "en-US-GuyNeural",
    "sonia": "en-GB-SoniaNeural",
    "brian": "en-GB-RyanNeural"
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
