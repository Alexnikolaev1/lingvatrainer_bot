"""
Edge TTS — бесплатная озвучка без API-ключа.
"""

import logging
import os
import tempfile
from typing import Optional

import edge_tts

from config import settings

logger = logging.getLogger(__name__)


async def text_to_speech(text: str, voice: Optional[str] = None) -> bytes:
    voice = voice or settings.TTS_VOICE
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        communicate = edge_tts.Communicate(text, voice, rate="+0%")
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.exception(f"Edge TTS error: {e}")
        return b""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def tts_to_voice_file(text: str, voice: Optional[str] = None) -> str:
    voice = voice or settings.TTS_VOICE
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        communicate = edge_tts.Communicate(text, voice, rate="+0%")
        await communicate.save(tmp_path)
        return tmp_path
    except Exception as e:
        logger.exception(f"Edge TTS file error: {e}")
        return ""
