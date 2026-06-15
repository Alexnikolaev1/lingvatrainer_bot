"""
LINGVA.AI — персональный AI-репетитор английского.
"""

import asyncio
import logging
import os
import sys

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
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

APP_VERSION = "1.3.0-railway"
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


def _say(msg: str) -> None:
    print(msg, flush=True)
    logger.info(msg)


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


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="OK", content_type="text/plain")


async def root_handler(_request: web.Request) -> web.Response:
    mode = "webhook" if get_webhook_url() else "polling"
    return web.Response(text=f"LINGVA.AI v{APP_VERSION} ({mode})", content_type="text/plain")


def _is_production() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_ID")
        or os.getenv("PORT")
    )


async def run_railway() -> None:
    _say(f"=== LINGVA.AI v{APP_VERSION} ===")

    bot = create_bot()
    dp = create_dispatcher()
    port = int(os.getenv("PORT", 8080))
    webhook_base = get_webhook_url()

    me = await bot.get_me()
    _say(f"Bot: @{me.username}")

    wh_info = await bot.get_webhook_info()
    _say(f"Webhook до старта: {wh_info.url or '(нет)'}")

    await init_db()
    _say(f"DB: {settings.DB_PATH}")

    asyncio.create_task(start_scheduler(bot))

    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", root_handler)

    poll_task = None

    if webhook_base:
        url = f"{webhook_base.rstrip('/')}{WEBHOOK_PATH}"
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        await bot.set_webhook(url, drop_pending_updates=True)
        _say(f"MODE=webhook → {url}")
    else:
        if wh_info.url:
            await bot.delete_webhook(drop_pending_updates=True)
            _say(f"Удалён старый webhook: {wh_info.url}")

        poll_task = asyncio.create_task(
            dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        )
        _say("MODE=polling → бот опрашивает Telegram (нажми /start)")

        for key in sorted(os.environ):
            if key.startswith("RAILWAY_") and ("DOMAIN" in key or "URL" in key):
                _say(f"  env {key}={os.environ[key]}")

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=port).start()
    _say(f"HTTP :{port} ready")

    try:
        if poll_task:
            await poll_task
        else:
            stop = asyncio.Event()
            await stop.wait()
    finally:
        if poll_task and not poll_task.done():
            poll_task.cancel()
        await runner.cleanup()
        await bot.session.close()


async def run_local_polling() -> None:
    _say(f"=== LINGVA.AI v{APP_VERSION} local polling ===")
    bot = create_bot()
    dp = create_dispatcher()
    await init_db()
    asyncio.create_task(start_scheduler(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        if _is_production():
            asyncio.run(run_railway())
        else:
            asyncio.run(run_local_polling())
    except Exception as exc:
        _say(f"FATAL: {exc}")
        logger.exception("Crash")
        sys.exit(1)
