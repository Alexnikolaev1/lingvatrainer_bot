"""Статистика и настройки пользователя."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from database import db_execute, db_fetchone
from keyboards.common import lesson_settings_keyboard, level_keyboard, main_menu
from services.user import get_user_stats
from utils.text_utils import escape_html

logger = logging.getLogger(__name__)
router = Router()


def _xp_level(total_xp: int) -> str:
    if total_xp < 100:
        return "🌱 Новичок"
    if total_xp < 500:
        return "📗 Ученик"
    if total_xp < 1500:
        return "📘 Продвинутый"
    if total_xp < 5000:
        return "📙 Эксперт"
    return "🏆 Мастер"


@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    stats = await get_user_stats(message.from_user.id)
    rank = _xp_level(stats["total_xp"])
    streak_emoji = "🔥" if stats["streak"] >= 3 else "📅"

    text = (
        f"📊 <b>Твой прогресс</b>\n\n"
        f"👤 {escape_html(stats['username'])}\n"
        f"📈 Уровень CEFR: <b>{stats['level']}</b>\n"
        f"{rank} — <b>{stats['total_xp']}</b> XP\n"
        f"{streak_emoji} Streak: <b>{stats['streak']}</b> дн.\n"
        f"⭐ XP за неделю: <b>{stats['week_xp']}</b>\n\n"
        f"📚 Слов в словаре: <b>{stats['vocab_count']}</b>\n"
        f"🔁 Ждут повторения: <b>{stats['due_count']}</b>\n"
        f"✅ Всего повторений: <b>{stats['reviews_total']}</b>"
    )
    await message.answer(text, reply_markup=main_menu())


@router.message(Command("settings"))
async def cmd_settings(message: types.Message) -> None:
    user_id = message.from_user.id
    row = await db_fetchone(
        """SELECT level, morning_window, evening_window,
                  lessons_enabled, words_per_lesson, timezone
           FROM users WHERE user_id=?""",
        (user_id,),
    )

    level = row["level"] if row else "A2"
    morning = row["morning_window"] if row else "08:00-10:00"
    evening = row["evening_window"] if row else "18:00-20:00"
    lessons_on = row["lessons_enabled"] if row else 1
    words = row["words_per_lesson"] if row else 2
    tz = row["timezone"] if row else "Europe/Moscow"

    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"📈 Уровень: <b>{level}</b>\n"
        f"🕐 Часовой пояс: <b>{tz}</b>\n"
        f"🌅 Утро (новые слова): {morning}\n"
        f"🌆 Вечер (фраза + упражнение): {evening}\n"
        f"📬 Уроки: <b>{'вкл' if lessons_on else 'выкл'}</b>, {words} слов/утро\n\n"
        f"/lesson — урок сейчас\n\n"
        "Уровень CEFR:",
        reply_markup=level_keyboard("set_level"),
    )
    await message.answer(
        "📬 <b>Расписание уроков</b>",
        reply_markup=lesson_settings_keyboard(bool(lessons_on), words or 2),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("set_level:"))
async def callback_set_level(callback: types.CallbackQuery) -> None:
    level = callback.data.split(":")[1]
    await db_execute("UPDATE users SET level=? WHERE user_id=?", (level, callback.from_user.id))
    await callback.message.edit_text(f"✅ Уровень установлен: <b>{level}</b>")
    await callback.answer(f"Уровень: {level}")


@router.callback_query(lambda c: c.data == "lesson_toggle")
async def callback_lesson_toggle(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    row = await db_fetchone("SELECT lessons_enabled, words_per_lesson FROM users WHERE user_id=?", (user_id,))
    current = row["lessons_enabled"] if row else 1
    words = row["words_per_lesson"] if row else 2
    new_val = 0 if current else 1
    await db_execute("UPDATE users SET lessons_enabled=? WHERE user_id=?", (new_val, user_id))
    await callback.message.edit_reply_markup(
        reply_markup=lesson_settings_keyboard(bool(new_val), words or 2)
    )
    await callback.answer("Уроки включены" if new_val else "Уроки выключены")


@router.callback_query(lambda c: c.data and c.data.startswith("lesson_words:"))
async def callback_lesson_words(callback: types.CallbackQuery) -> None:
    count = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await db_execute("UPDATE users SET words_per_lesson=? WHERE user_id=?", (count, user_id))
    row = await db_fetchone("SELECT lessons_enabled FROM users WHERE user_id=?", (user_id,))
    enabled = bool(row["lessons_enabled"]) if row else True
    await callback.message.edit_reply_markup(
        reply_markup=lesson_settings_keyboard(enabled, count)
    )
    await callback.answer(f"{count} слов в утреннем уроке")
