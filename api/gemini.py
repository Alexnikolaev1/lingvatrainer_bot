"""
Унифицированный AI-клиент: Gemini → Groq LLM (оба бесплатные).
"""

import asyncio
import logging
import time
from typing import Optional

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

_global_lock = asyncio.Lock()
_global_calls: list[float] = []
_user_calls: dict[int, list[float]] = {}
_groq_calls: list[float] = []


def _clean_old_calls(calls: list[float], window: float = 60.0) -> list[float]:
    now = time.monotonic()
    return [t for t in calls if now - t < window]


async def _check_gemini_limit(user_id: Optional[int]) -> bool:
    async with _global_lock:
        global _global_calls
        _global_calls = _clean_old_calls(_global_calls)
        if len(_global_calls) >= settings.GEMINI_RPM_LIMIT:
            return False
        if user_id is not None:
            user_c = _clean_old_calls(_user_calls.get(user_id, []))
            _user_calls[user_id] = user_c
            if len(user_c) >= settings.GEMINI_USER_RPM_LIMIT:
                return False
        now = time.monotonic()
        _global_calls.append(now)
        if user_id is not None:
            _user_calls.setdefault(user_id, []).append(now)
    return True


async def _check_groq_limit() -> bool:
    async with _global_lock:
        global _groq_calls
        _groq_calls = _clean_old_calls(_groq_calls)
        if len(_groq_calls) >= settings.GROQ_RPM_LIMIT:
            return False
        _groq_calls.append(time.monotonic())
    return True


async def generate_text(
    prompt: str,
    user_id: Optional[int] = None,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    system: Optional[str] = None,
) -> str:
    """
    Сгенерировать текст через цепочку провайдеров:
    1. Gemini (основной)
    2. Groq LLM (резервный, бесплатный)
    """
    if settings.GEMINI_API_KEY and await _check_gemini_limit(user_id):
        result = await _gemini_request(prompt, max_tokens, temperature, system)
        if result and not result.startswith("❌"):
            return result
        logger.warning("Gemini недоступен, переключаюсь на Groq")

    if settings.GROQ_API_KEY and await _check_groq_limit():
        result = await _groq_request(prompt, max_tokens, temperature, system)
        if result:
            return result

    return "⚠️ AI временно недоступен. Попробуй через минуту."


async def _gemini_request(
    prompt: str,
    max_tokens: int,
    temperature: float,
    system: Optional[str],
) -> str:
    url = settings.GEMINI_API_URL.format(
        model=settings.GEMINI_MODEL,
        key=settings.GEMINI_API_KEY,
    )

    payload: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=45)
            ) as resp:
                if resp.status == 429:
                    return ""
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Gemini {resp.status}: {body[:200]}")
                    return ""

                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                parts_out = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts_out).strip()

    except asyncio.TimeoutError:
        logger.error("Gemini timeout")
        return ""
    except Exception as e:
        logger.exception(f"Gemini error: {e}")
        return ""


async def _groq_request(
    prompt: str,
    max_tokens: int,
    temperature: float,
    system: Optional[str],
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.GROQ_LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.GROQ_CHAT_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Groq LLM {resp.status}: {body[:200]}")
                    return ""
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception(f"Groq LLM error: {e}")
        return ""
