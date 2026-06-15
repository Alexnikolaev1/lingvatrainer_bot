"""
Конфигурация LINGVA.AI.
Все переменные окружения загружаются здесь и доступны через объект settings.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


def _resolve_webhook_url() -> Optional[str]:
    """Собрать публичный URL для Telegram webhook (читается при каждом старте)."""
    explicit = os.getenv("WEBHOOK_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    # Railway: приоритетные переменные
    for key in ("RAILWAY_STATIC_URL", "RAILWAY_PUBLIC_DOMAIN"):
        value = os.getenv(key, "").strip()
        if not value:
            continue
        if value.startswith("http://") or value.startswith("https://"):
            return value.rstrip("/")
        return f"https://{value}"

    # Любая Railway-переменная с доменом
    for key, value in os.environ.items():
        if not key.startswith("RAILWAY_") or not value:
            continue
        if "DOMAIN" not in key and "URL" not in key:
            continue
        v = value.strip()
        if "railway.app" in v or "railway.dev" in v:
            if v.startswith("http://") or v.startswith("https://"):
                return v.rstrip("/")
            return f"https://{v}"

    return None


def get_webhook_url() -> Optional[str]:
    """Актуальный webhook URL (вызов в runtime, не из кэша settings)."""
    return _resolve_webhook_url()


def _is_railway() -> bool:
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_ID"))


def _resolve_db_path() -> str:
    """
    Путь к SQLite. На Railway по умолчанию /app/data (writable без volume).
    Volume опционален: смонтируйте на /app/data для персистентности.
    """
    explicit = os.getenv("DB_PATH", "").strip()
    if explicit:
        return explicit
    if _is_railway() or os.getenv("PORT"):
        return "/app/data/lingva.db"
    return "lingva.db"


def _parse_allowed_user_ids() -> Optional[frozenset]:
    """
    ALLOWED_USER_IDS=123456789 или 123,456,789
    Пусто → доступ для всех.
    """
    raw = os.getenv("ALLOWED_USER_IDS", "").strip()
    if not raw:
        return None
    ids = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids) if ids else None


@dataclass
class Settings:
    # === Telegram ===
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))

    # === Вебхук ===
    WEBHOOK_URL: Optional[str] = field(default_factory=lambda: _resolve_webhook_url())

    # === AI API (все с бесплатными тирами) ===
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))

    # === Новости (опционально; по умолчанию — бесплатные RSS) ===
    NEWSAPI_KEY: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))

    # === Gemini (бесплатный тир: только Flash / Flash-Lite) ===
    # ⚠ gemini-2.0-flash отключена с 01.06.2026 — используйте 2.5-flash-lite
    GEMINI_MODEL: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    )
    GEMINI_API_URL: str = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent?key={key}"
    )

    # === Groq (Whisper + LLM fallback) ===
    GROQ_WHISPER_URL: str = "https://api.groq.com/openai/v1/audio/transcriptions"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"
    GROQ_CHAT_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_LLM_MODEL: str = field(
        default_factory=lambda: os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")
    )

    # === Edge TTS (бесплатно, без ключа) ===
    TTS_VOICE: str = field(default_factory=lambda: os.getenv("TTS_VOICE", "en-US-AriaNeural"))

    # === Rate limiting (консервативно под free tier) ===
    # Gemini 2.5 Flash-Lite free: ~30 RPM, ~1500 RPD (см. ai.google.dev)
    GEMINI_RPM_LIMIT: int = 25
    GEMINI_USER_RPM_LIMIT: int = 5
    # Groq free: 30 RPM LLM, 20 RPM Whisper
    GROQ_RPM_LIMIT: int = 25

    # === Кэш ===
    NEWS_CACHE_TTL_HOURS: int = 3
    DATAMUSE_CACHE_TTL_HOURS: int = 24

    # === SQLite ===
    DB_PATH: str = field(default_factory=_resolve_db_path)

    # === Доступ ===
    # ALLOWED_USER_IDS=123456789 — только эти Telegram user ID (через запятую)
    allowed_user_ids: Optional[frozenset] = field(default_factory=_parse_allowed_user_ids)

    # === Диалог ===
    TALK_HISTORY_SIZE: int = 12

    # === SRS ===
    QUIZ_SIZE: int = 7

    def __post_init__(self) -> None:
        if not self.BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN не задан!")


settings = Settings()
