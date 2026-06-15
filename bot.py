"""
LINGVA.AI — персональный AI-репетитор английского.
"""

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import settings
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

APP_VERSION = "1.1.0-railway"

WEBHOOK_PATH = f"/webhook/{settings.BOT_TOKEN}"

ROUTERS = [
    start_router,
    talk_router,      # talk до speech — перехват голосовых в диалоге
    vocab_router,
    review_router,
    speech_router,
    listening_router,
    reading_router,
    grammar_router,
    stats_router,
]


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


async def on_startup(bot: Bot) -> None:
    logger.info("LINGVA.AI v%s", APP_VERSION)
    logger.info("Startup: railway=%s port=%s webhook=%s",
                os.getenv("RAILWAY_ENVIRONMENT"), os.getenv("PORT"), settings.WEBHOOK_URL)
    logger.info("Gemini model: %s", settings.GEMINI_MODEL)
    logger.info("DB path: %s", settings.DB_PATH)

    try:
        await init_db()
        logger.info("БД инициализирована.")
    except Exception:
        logger.exception("Ошибка инициализации БД — сервер продолжит работу")

    if "2.0-flash" in settings.GEMINI_MODEL:
        logger.error(
            "Модель %s отключена Google с 01.06.2026! "
            "Установите GEMINI_MODEL=gemini-2.5-flash-lite",
            settings.GEMINI_MODEL,
        )

    if settings.WEBHOOK_URL:
        url = f"{settings.WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(url)
            logger.info("Webhook установлен: %s", url)
        except Exception:
            logger.exception("Не удалось установить webhook — бот ответит после redeploy")
    else:
        logger.warning("WEBHOOK_URL не задан — нужен public domain на Railway")

    asyncio.create_task(start_scheduler(bot))


async def on_shutdown(bot: Bot) -> None:
    if settings.WEBHOOK_URL:
        await bot.delete_webhook()


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="OK", content_type="text/plain")


async def root_handler(_request: web.Request) -> web.Response:
    return web.Response(text="LINGVA.AI bot is running", content_type="text/plain")


def create_app() -> web.Application:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

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
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def _use_web_server() -> bool:
    """На Railway всегда HTTP (healthcheck). Локально — polling без PORT."""
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_ID"):
        return True
    if os.getenv("PORT"):
        return True
    if settings.WEBHOOK_URL:
        return True
    return False


if __name__ == "__main__":
    mode = "webhook" if _use_web_server() else "polling"
    logger.info("Boot mode=%s v%s", mode, APP_VERSION)

    if _use_web_server():
        port = int(os.getenv("PORT", 8080))
        logger.info("HTTP server on 0.0.0.0:%s (webhook=%s)", port, settings.WEBHOOK_URL)
        web.run_app(create_app(), host="0.0.0.0", port=port)
    else:
        logger.info("Polling mode (local dev)")
        asyncio.run(run_polling())
