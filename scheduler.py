"""Планировщик напоминаний о повторениях."""

import asyncio
import logging
import random
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database import db_fetchall, db_fetchone

logger = logging.getLogger(__name__)

_last_notified: dict[int, str] = {}


def _parse_window(window_str: str) -> tuple[int, int, int, int]:
    try:
        start, end = window_str.split("-")
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        return sh, sm, eh, em
    except Exception:
        return 8, 0, 10, 0


def _now_in_window(window_str: str) -> bool:
    sh, sm, eh, em = _parse_window(window_str)
    now = datetime.now(timezone.utc)
    current = now.hour * 60 + now.minute
    return sh * 60 + sm <= current <= eh * 60 + em


async def _check_and_notify(bot: Bot) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    users = await db_fetchall(
        """
        SELECT DISTINCT u.user_id, u.morning_window, u.evening_window
        FROM users u
        JOIN vocabulary v ON v.user_id = u.user_id
        WHERE v.next_review <= CURRENT_TIMESTAMP
        """
    )

    for user in users:
        user_id = user["user_id"]
        if _last_notified.get(user_id) == today:
            continue

        morning = user["morning_window"] or "08:00-10:00"
        evening = user["evening_window"] or "18:00-20:00"
        if not (_now_in_window(morning) or _now_in_window(evening)):
            continue

        if random.random() > 0.2:
            continue

        count_row = await db_fetchone(
            "SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=? AND next_review<=CURRENT_TIMESTAMP",
            (user_id,),
        )
        count = count_row["cnt"] if count_row else 0
        if count == 0:
            continue

        try:
            await bot.send_message(
                user_id,
                f"🔔 <b>Время повторить!</b>\n\n"
                f"📚 <b>{count}</b> слов ждут.\n/review — начать",
            )
            _last_notified[user_id] = today
        except TelegramForbiddenError:
            logger.warning(f"User {user_id} blocked bot")
        except TelegramBadRequest as e:
            logger.error(f"Notify error {user_id}: {e}")


async def start_scheduler(bot: Bot) -> None:
    logger.info("Scheduler started.")
    while True:
        try:
            await _check_and_notify(bot)
        except Exception as e:
            logger.exception(f"Scheduler error: {e}")
        await asyncio.sleep(60)
