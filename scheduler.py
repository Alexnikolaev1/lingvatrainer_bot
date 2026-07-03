"""Планировщик: проактивные уроки + напоминания о повторении."""

import asyncio
import logging
import random
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import settings
from database import db_execute, db_fetchall, db_fetchone
from services.lessons import deliver_evening_lesson, deliver_morning_lesson, user_local_now

logger = logging.getLogger(__name__)


def _parse_window(window_str: str) -> tuple[int, int, int, int]:
    try:
        start, end = window_str.split("-")
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        return sh, sm, eh, em
    except Exception:
        return 8, 0, 10, 0


def _in_window(window_str: str, tz_name: str) -> bool:
    """Проверить, попадает ли локальное время пользователя в окно HH:MM-HH:MM."""
    sh, sm, eh, em = _parse_window(window_str or "08:00-10:00")
    now = user_local_now(tz_name)
    current = now.hour * 60 + now.minute
    return sh * 60 + sm <= current <= eh * 60 + em


def _today_local(tz_name: str) -> str:
    return user_local_now(tz_name).strftime("%Y-%m-%d")


async def _get_lesson_users() -> list:
    return await db_fetchall(
        """
        SELECT user_id, level, timezone, morning_window, evening_window,
               words_per_lesson, lessons_enabled,
               last_morning_lesson, last_evening_lesson
        FROM users
        WHERE COALESCE(lessons_enabled, 1) = 1
        """
    )


async def _check_and_deliver(bot: Bot) -> None:
    users = await _get_lesson_users()

    for user in users:
        user_id = user["user_id"]
        if settings.allowed_user_ids and user_id not in settings.allowed_user_ids:
            continue

        tz = user["timezone"] or "Europe/Moscow"
        today = _today_local(tz)
        morning = user["morning_window"] or "08:00-10:00"
        evening = user["evening_window"] or "18:00-20:00"
        word_count = user["words_per_lesson"] or 2

        # Утренний урок: новые слова + грамматика
        if (
            _in_window(morning, tz)
            and user["last_morning_lesson"] != today
            and random.random() < 0.3
        ):
            try:
                logger.info("Morning lesson → user %s", user_id)
                await deliver_morning_lesson(bot, user_id, word_count)
            except Exception as e:
                logger.exception("Morning lesson error %s: %s", user_id, e)

        # Вечерний урок: фраза + упражнение + напоминание о повторении
        elif (
            _in_window(evening, tz)
            and user["last_evening_lesson"] != today
            and random.random() < 0.3
        ):
            try:
                logger.info("Evening lesson → user %s", user_id)
                await deliver_evening_lesson(bot, user_id)
            except Exception as e:
                logger.exception("Evening lesson error %s: %s", user_id, e)

        # Дополнительно: короткое напоминание если много слов на повторение
        elif _in_window(evening, tz) and random.random() < 0.15:
            count_row = await db_fetchone(
                "SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=? AND next_review<=CURRENT_TIMESTAMP",
                (user_id,),
            )
            count = count_row["cnt"] if count_row else 0
            if count >= 5:
                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 <b>Напоминание</b>\n\n"
                        f"📚 <b>{count}</b> слов ждут повторения.\n"
                        f"/review — начать сейчас",
                    )
                except (TelegramForbiddenError, TelegramBadRequest):
                    pass


async def start_scheduler(bot: Bot) -> None:
    logger.info("Scheduler started (lessons + reviews).")
    while True:
        try:
            await _check_and_deliver(bot)
        except Exception as e:
            logger.exception("Scheduler error: %s", e)
        await asyncio.sleep(60)
