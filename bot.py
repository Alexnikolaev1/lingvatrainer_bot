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
    await init_db()
    logger.info("БД инициализирована.")
    logger.info("Gemini model: %s", settings.GEMINI_MODEL)
    logger.info("Groq LLM: %s", settings.GROQ_LLM_MODEL)
    logger.info("DB path: %s", settings.DB_PATH)

    if "2.0-flash" in settings.GEMINI_MODEL:
        logger.error(
            "Модель %s отключена Google с 01.06.2026! "
            "Установите GEMINI_MODEL=gemini-2.5-flash-lite",
            settings.GEMINI_MODEL,
        )

    if settings.WEBHOOK_URL:
        url = f"{settings.WEBHOOK_URL}{WEBHOOK_PATH}"
        await bot.set_webhook(url)
        logger.info(f"Webhook: {url}")
    else:
        logger.info("Polling mode.")

    asyncio.create_task(start_scheduler(bot))


async def on_shutdown(bot: Bot) -> None:
    if settings.WEBHOOK_URL:
        await bot.delete_webhook()


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="OK")


def create_app() -> web.Application:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
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


if __name__ == "__main__":
    if settings.WEBHOOK_URL:
        port = int(os.getenv("PORT", 8080))
        logger.info(f"Webhook server on port {port}")
        web.run_app(create_app(), host="0.0.0.0", port=port)
    else:
        asyncio.run(run_polling())
