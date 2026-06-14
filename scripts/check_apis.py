#!/usr/bin/env python3
"""
Проверка API-ключей и доступности моделей перед деплоем.
Запуск: python scripts/check_apis.py
"""

import asyncio
import os
import sys

# корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from config import settings


async def check_gemini() -> bool:
    if not settings.GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY не задан")
        return False

    url = settings.GEMINI_API_URL.format(
        model=settings.GEMINI_MODEL,
        key=settings.GEMINI_API_KEY,
    )
    payload = {
        "contents": [{"parts": [{"text": "Say OK"}]}],
        "generationConfig": {"maxOutputTokens": 10},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                body = await resp.text()
                if resp.status == 200:
                    print(f"✅ Gemini ({settings.GEMINI_MODEL}): OK")
                    return True
                if resp.status == 404 and "2.0-flash" in settings.GEMINI_MODEL:
                    print(f"❌ Gemini: модель {settings.GEMINI_MODEL} отключена с 01.06.2026")
                    print("   → установите GEMINI_MODEL=gemini-2.5-flash-lite")
                else:
                    print(f"❌ Gemini {resp.status}: {body[:200]}")
                return False
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return False


async def check_groq_llm() -> bool:
    if not settings.GROQ_API_KEY:
        print("❌ GROQ_API_KEY не задан")
        return False

    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    payload = {
        "model": settings.GROQ_LLM_MODEL,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.GROQ_CHAT_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    print(f"✅ Groq LLM ({settings.GROQ_LLM_MODEL}): OK")
                    return True
                body = await resp.text()
                print(f"❌ Groq LLM {resp.status}: {body[:200]}")
                return False
    except Exception as e:
        print(f"❌ Groq LLM error: {e}")
        return False


async def check_telegram() -> bool:
    if not settings.BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не задан")
        return False
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getMe"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    name = data["result"].get("username", "?")
                    print(f"✅ Telegram bot: @{name}")
                    return True
                print(f"❌ Telegram: {data}")
                return False
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


async def main() -> None:
    print("=== LINGVA.AI — проверка API ===\n")
    print(f"Модель Gemini: {settings.GEMINI_MODEL}")
    print(f"Webhook URL:   {settings.WEBHOOK_URL or '(polling)'}\n")

    results = await asyncio.gather(
        check_telegram(),
        check_gemini(),
        check_groq_llm(),
    )
    print()
    if all(results):
        print("🎉 Все проверки пройдены — можно деплоить.")
    else:
        print("⚠️  Есть проблемы — исправьте перед деплоем.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
