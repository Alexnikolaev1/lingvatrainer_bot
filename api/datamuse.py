"""
Datamuse API — бесплатные синонимы и антонимы.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp

from database import db_execute, db_fetchone

logger = logging.getLogger(__name__)

DATAMUSE_BASE = "https://api.datamuse.com/words"
CACHE_TTL_HOURS = 24


async def _get_cached(key: str) -> Optional[List[str]]:
    row = await db_fetchone("SELECT data, expires_at FROM cache WHERE key=?", (key,))
    if not row:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        await db_execute("DELETE FROM cache WHERE key=?", (key,))
        return None
    try:
        return json.loads(row["data"])
    except json.JSONDecodeError:
        return None


async def _set_cache(key: str, data: List[str]) -> None:
    expires_at = (datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    await db_execute(
        "INSERT OR REPLACE INTO cache(key, data, expires_at) VALUES (?, ?, ?)",
        (key, json.dumps(data), expires_at),
    )


async def _fetch_datamuse(params: dict) -> List[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                DATAMUSE_BASE,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                items = await resp.json()
                return [item["word"] for item in items[:5]]
    except Exception as e:
        logger.exception(f"Datamuse error: {e}")
        return []


async def get_synonyms(word: str) -> List[str]:
    cache_key = f"syn:{word.lower()}"
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached
    result = await _fetch_datamuse({"ml": word, "max": 5})
    await _set_cache(cache_key, result)
    return result


async def get_antonyms(word: str) -> List[str]:
    cache_key = f"ant:{word.lower()}"
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached
    result = await _fetch_datamuse({"rel_ant": word, "max": 5})
    await _set_cache(cache_key, result)
    return result
