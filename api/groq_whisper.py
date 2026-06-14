"""
Groq Whisper — бесплатная транскрипция речи.
"""

import logging
from typing import Optional

import aiohttp

from config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> Optional[str]:
    if not settings.GROQ_API_KEY:
        logger.error("GROQ_API_KEY не задан — транскрипция недоступна")
        return None

    content_type = "audio/ogg" if filename.endswith(".ogg") else "audio/mpeg"
    form = aiohttp.FormData()
    form.add_field("file", audio_bytes, filename=filename, content_type=content_type)
    form.add_field("model", settings.GROQ_WHISPER_MODEL)
    form.add_field("language", "en")
    form.add_field("response_format", "json")

    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.GROQ_WHISPER_URL,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("text", "").strip()
                    logger.info(f"Whisper: '{text[:80]}'")
                    return text
                body = await resp.text()
                logger.error(f"Groq Whisper {resp.status}: {body[:300]}")
                return None
    except Exception as e:
        logger.exception(f"Groq Whisper error: {e}")
        return None
