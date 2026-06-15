"""
LINGVA.AI — персональный AI-репетитор английского.
"""

import asyncio
import logging
import os

from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import get_webhook_url, settings
from database import init_db
from handlers.grammar import router as grammar_router
from handlers.listening import router as listening_router
from handlers.reading import router as reading_router
from handlers.review import router as review_router
from handlers.speech import router as speech_router
from handlers.start import router as start_router
from handlers.stats import router as stats_router
from handlers.talk import router as talk_router
from handlers.vocabulary import router as vocab_router
from middleware.user import UserMiddleware
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

APP_VERSION = "1.2.0-railway"

WEBHOOK_PATH = f"/webhook/{settings.BOT_TOKEN}"

ROUTERS = [
    start_router,
    talk_router,
    vocab_router,
    review_router,
    speech_router,
    listening_router,
    reading_router,
    grammar_router,
    stats_router,
]

_polling_task: Optional[asyncio.Task] = None


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(UserMiddleware())
    for router in ROUTERS:
        dp.include_router(router)
    return dp


def _log_railway_env() -> None:
    for key in sorted(os.environ):
        if key.startswith("RAILWAY_") and ("DOMAIN" in key or "URL" in key):
            logger.info("env %s=%s", key, os.environ[key])


def _make_on_startup(dp: Dispatcher, *, web_server: bool = False):
    async def on_startup(bot: Bot) -> None:
        global _polling_task
        webhook_base = get_webhook_url()

        logger.info("LINGVA.AI v%s", APP_VERSION)
        logger.info(
            "Startup: railway=%s port=%s mode=%s",
            os.getenv("RAILWAY_ENVIRONMENT"),
            os.getenv("PORT"),
            "webhook" if webhook_base else "polling-fallback",
        )
        logger.info("Gemini model: %s", settings.GEMINI_MODEL)
        logger.info("DB path: %s", settings.DB_PATH)

        if not webhook_base:
            _log_railway_env()

        try:
            await init_db()
            logger.info("БД инициализирована.")
        except Exception:
            logger.exception("Ошибка инициализации БД")

        if "2.0-flash" in settings.GEMINI_MODEL:
            logger.error("Модель %s отключена! Используйте gemini-2.5-flash-lite", settings.GEMINI_MODEL)

        if webhook_base:
            url = f"{webhook_base.rstrip('/')}{WEBHOOK_PATH}"
            try:
                await bot.set_webhook(url, drop_pending_updates=True)
                logger.info("Webhook установлен: %s", url)
            except Exception:
                logger.exception("Не удалось установить webhook")
        elif web_server:
            logger.warning(
                "Публичный домен не найден → polling fallback.\n"
                "Для webhook: Railway → Settings → Networking → Generate Domain,\n"
                "затем Variables → WEBHOOK_URL=https://ВАШ-ДОМЕН.up.railway.app"
            )
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                _polling_task = asyncio.create_task(
                    dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                )
                logger.info("Polling запущен — бот должен отвечать на /start")
            except Exception:
                logger.exception("Не удалось запустить polling")
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Polling mode (local)")

        asyncio.create_task(start_scheduler(bot))

    return on_startup


def _make_on_shutdown():
    async def on_shutdown(bot: Bot) -> None:
        global _polling_task
        if _polling_task and not _polling_task.done():
            _polling_task.cancel()
            try:
                await _polling_task
            except asyncio.CancelledError:
                pass
        await bot.delete_webhook()

    return on_shutdown


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="OK", content_type="text/plain")


async def root_handler(_request: web.Request) -> web.Response:
    mode = "webhook" if get_webhook_url() else "polling"
    return web.Response(
        text=f"LINGVA.AI v{APP_VERSION} ({mode})",
        content_type="text/plain",
    )


def create_app() -> web.Application:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(_make_on_startup(dp, web_server=True))
    dp.shutdown.register(_make_on_shutdown())

    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/health", health_handler)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app


async def run_polling() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(_make_on_startup(dp, web_server=False))
    dp.shutdown.register(_make_on_shutdown())
    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def _use_web_server() -> bool:
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_ID"):
        return True
    if os.getenv("PORT"):
        return True
    if get_webhook_url():
        return True
    return False


if __name__ == "__main__":
    webhook = get_webhook_url()
    mode = "webhook" if webhook else ("web+poll" if _use_web_server() else "polling")
    logger.info("Boot mode=%s v%s", mode, APP_VERSION)

    if _use_web_server():
        port = int(os.getenv("PORT", 8080))
        logger.info("HTTP server on 0.0.0.0:%s (webhook=%s)", port, webhook)
        web.run_app(create_app(), host="0.0.0.0", port=port)
    else:
        asyncio.run(run_polling())
