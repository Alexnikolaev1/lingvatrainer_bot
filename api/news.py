"""
Новости: бесплатные RSS-ленты (без API-ключа) + опциональный NewsAPI.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from typing import Optional

import aiohttp

from config import settings
from database import db_execute, db_fetchone

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"

# Бесплатные RSS-ленты на английском
RSS_FEEDS = [
    ("BBC Learning English", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ("Reuters", "https://feeds.reuters.com/reuters/topNews"),
]


async def get_latest_news() -> Optional[str]:
    cached = await _get_cached_news()
    if cached:
        return cached

    # Сначала пробуем RSS (бесплатно)
    for source, url in RSS_FEEDS:
        text = await _fetch_rss(url, source)
        if text:
            await _cache_news(text, source)
            return text

    # Fallback на NewsAPI если ключ есть
    if settings.NEWSAPI_KEY:
        return await _fetch_newsapi()

    return None


async def _fetch_rss(url: str, source: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                xml_text = await resp.text()

        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = _tag_text(item, "title")
            description = _tag_text(item, "description") or _tag_text(item, "summary")
            if title and len(description) > 30:
                clean_desc = _strip_html(description)
                return f"{title}\n\n{clean_desc}"
        return None
    except Exception as e:
        logger.warning(f"RSS {source} error: {e}")
        return None


def _tag_text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    if el is not None and el.text:
        return unescape(el.text.strip())
    # Atom namespace
    for child in item:
        if child.tag.endswith(tag) and child.text:
            return unescape(child.text.strip())
    return ""


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _fetch_newsapi() -> Optional[str]:
    try:
        params = {
            "apiKey": settings.NEWSAPI_KEY,
            "country": "us",
            "category": "general",
            "pageSize": 5,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                NEWSAPI_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                for article in data.get("articles", []):
                    content = article.get("content") or article.get("description") or ""
                    title = article.get("title", "")
                    if title and len(content) > 50:
                        full_text = f"{title}\n\n{content}"
                        await _cache_news(
                            full_text,
                            article.get("source", {}).get("name", "NewsAPI"),
                        )
                        return full_text
        return None
    except Exception as e:
        logger.exception(f"NewsAPI error: {e}")
        return None


async def _get_cached_news() -> Optional[str]:
    threshold = (datetime.utcnow() - timedelta(hours=settings.NEWS_CACHE_TTL_HOURS)).isoformat()
    row = await db_fetchone(
        "SELECT content FROM news_cache WHERE fetched_at >= ? ORDER BY id DESC LIMIT 1",
        (threshold,),
    )
    return row["content"] if row else None


async def _cache_news(content: str, source: str) -> None:
    await db_execute(
        "INSERT INTO news_cache(source, content, fetched_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (source, content),
    )
    await db_execute(
        "DELETE FROM news_cache WHERE id NOT IN (SELECT id FROM news_cache ORDER BY id DESC LIMIT 10)"
    )
