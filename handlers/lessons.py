"""Проактивные уроки: /lesson и быстрые действия."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from database import db_fetchone
from handlers.listening import cmd_listening
from handlers.reading import cmd_read
from handlers.review import start_review_session
from handlers.talk import cmd_talk
from services.lessons import deliver_evening_lesson, deliver_morning_lesson

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("lesson"))
async def cmd_lesson(message: types.Message) -> None:
    """Получить урок прямо сейчас."""
    user_id = message.from_user.id
    row = await db_fetchone(
        "SELECT words_per_lesson FROM users WHERE user_id=?", (user_id,)
    )
    word_count = row["words_per_lesson"] if row and row["words_per_lesson"] else 2

    loading = await message.answer("📚 Готовлю урок...")

    ok = await deliver_morning_lesson(message.bot, user_id, word_count)
    if ok:
        await loading.delete()
    else:
        await loading.edit_text("❌ Не удалось сгенерировать урок. Попробуй позже.")


@router.message(Command("lesson_evening"))
async def cmd_lesson_evening(message: types.Message) -> None:
    """Вечерний мини-урок по запросу."""
    loading = await message.answer("🌆 Готовлю вечерний урок...")
    ok = await deliver_evening_lesson(message.bot, message.from_user.id)
    if ok:
        await loading.delete()
    else:
        await loading.edit_text("❌ Не удалось. Попробуй позже.")


@router.callback_query(lambda c: c.data and c.data.startswith("lesson:"))
async def callback_lesson_action(callback: types.CallbackQuery) -> None:
    action = callback.data.split(":")[1]
    await callback.answer()

    if action == "review":
        await start_review_session(callback.message, callback.from_user.id)
    elif action == "listening":
        await cmd_listening(callback.message)
    elif action == "read":
        await cmd_read(callback.message)
    elif action == "talk":
        await cmd_talk(callback.message)
