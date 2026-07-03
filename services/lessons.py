"""
Генерация и доставка проактивных уроков: новые слова, грамматика, фразы.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api.gemini import generate_text
from database import db_execute, db_fetchall, db_fetchone, db_lastrowid
from services.user import get_user_level
from utils.text_utils import escape_html, format_word_card, parse_json_safe

logger = logging.getLogger(__name__)

MORNING_PROMPT = """Ты — преподаватель английского. Составь УТРЕННИЙ урок для уровня {level}.

Придумай ровно {count} новых полезных английских слова или коротких выражения.
НЕ используй слова из списка: {exclude}

Добавь мини-урок грамматики (2-3 предложения по-русски).

JSON:
{{
  "words": [
    {{
      "word": "слово",
      "translation": "перевод",
      "level": "{level}",
      "etymology": "мнемоника",
      "examples": [{{"en": "пример", "ru": "перевод"}}]
    }}
  ],
  "grammar": {{
    "title": "название правила",
    "rule": "объяснение по-русски",
    "example_en": "пример на английском",
    "example_ru": "перевод примера"
  }}
}}

Только JSON."""

EVENING_PROMPT = """Ты — преподаватель английского. Составь ВЕЧЕРНИЙ мини-урок для уровня {level}.

JSON:
{{
  "phrase": {{
    "en": "идиома или полезная фраза",
    "ru": "перевод",
    "example": "пример в предложении на английском"
  }},
  "exercise": {{
    "question": "упражнение с пропуском ___",
    "hint": "подсказка",
    "answer": "правильный ответ"
  }},
  "tip": "мотивирующий совет на русском (1 предложение)"
}}

Только JSON."""


async def _known_words(user_id: int, limit: int = 40) -> List[str]:
    rows = await db_fetchall(
        "SELECT word FROM vocabulary WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    return [r["word"] for r in rows]


async def _save_lesson_word(user_id: int, word_data: dict) -> int:
    word = word_data.get("word", "").strip().lower()
    if not word:
        return 0

    existing = await db_fetchone(
        "SELECT id FROM vocabulary WHERE user_id=? AND LOWER(word)=LOWER(?)",
        (user_id, word),
    )
    examples = word_data.get("examples", [])
    examples_json = json.dumps(examples, ensure_ascii=False)

    if existing:
        await db_execute(
            """UPDATE vocabulary SET translation=?, examples=?, level=?
               WHERE id=?""",
            (word_data.get("translation", ""), examples_json,
             word_data.get("level", "?"), existing["id"]),
        )
        return existing["id"]

    return await db_lastrowid(
        """INSERT INTO vocabulary
           (user_id, word, translation, examples, level, synonyms, antonyms, next_review)
           VALUES (?, ?, ?, ?, ?, '[]', '[]', CURRENT_TIMESTAMP)""",
        (user_id, word, word_data.get("translation", ""),
         examples_json, word_data.get("level", "?")),
    )


def lesson_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Повторить", callback_data="lesson:review"),
                InlineKeyboardButton(text="🎧 Аудирование", callback_data="lesson:listening"),
            ],
            [
                InlineKeyboardButton(text="📰 Читать", callback_data="lesson:read"),
                InlineKeyboardButton(text="💬 Разговор", callback_data="lesson:talk"),
            ],
        ]
    )


async def build_morning_lesson(user_id: int, word_count: int = 2) -> Optional[str]:
    level = await get_user_level(user_id)
    exclude = ", ".join(await _known_words(user_id)) or "(пусто)"

    raw = await generate_text(
        MORNING_PROMPT.format(level=level, count=word_count, exclude=exclude),
        user_id=user_id,
        temperature=0.8,
    )
    data = parse_json_safe(raw, {})
    words = data.get("words", [])
    grammar = data.get("grammar", {})

    if not words:
        return None

    lines = ["🌅 <b>Доброе утро! Твой урок на сегодня</b>\n"]

    for w in words[:word_count]:
        await _save_lesson_word(user_id, w)
        card = format_word_card(
            word=w.get("word", "?"),
            translation=w.get("translation", ""),
            examples=w.get("examples", []),
            level=w.get("level", level),
            synonyms=[],
            antonyms=[],
            etymology=w.get("etymology", ""),
        )
        lines.append(card)
        lines.append("")

    if grammar:
        lines.append(
            f"✍️ <b>{escape_html(grammar.get('title', 'Грамматика'))}</b>\n"
            f"{escape_html(grammar.get('rule', ''))}\n\n"
            f"<i>{escape_html(grammar.get('example_en', ''))}</i>\n"
            f"🇷🇺 {escape_html(grammar.get('example_ru', ''))}"
        )

    lines.append("\n💡 Слова добавлены в словарь → /review вечером")
    return "\n".join(lines)


async def build_evening_lesson(user_id: int) -> Optional[str]:
    level = await get_user_level(user_id)
    raw = await generate_text(EVENING_PROMPT.format(level=level), user_id=user_id, temperature=0.8)
    data = parse_json_safe(raw, {})

    phrase = data.get("phrase", {})
    exercise = data.get("exercise", {})
    tip = data.get("tip", "")

    if not phrase and not exercise:
        return None

    lines = ["🌆 <b>Вечерний урок</b>\n"]

    if phrase:
        lines.append(
            f"💬 <b>Фраза дня:</b> <i>{escape_html(phrase.get('en', ''))}</i>\n"
            f"🇷🇺 {escape_html(phrase.get('ru', ''))}\n"
            f"📝 {escape_html(phrase.get('example', ''))}\n"
        )

    if exercise:
        lines.append(
            f"📝 <b>Упражнение:</b>\n{escape_html(exercise.get('question', ''))}\n"
            f"💡 <i>{escape_html(exercise.get('hint', ''))}</i>\n"
            f"<spoiler>✅ {escape_html(exercise.get('answer', ''))}</spoiler>"
        )

    due = await db_fetchone(
        "SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=? AND next_review<=CURRENT_TIMESTAMP",
        (user_id,),
    )
    due_count = due["cnt"] if due else 0
    if due_count > 0:
        lines.append(f"\n🔁 <b>{due_count}</b> слов ждут повторения → /review")

    if tip:
        lines.append(f"\n✨ {escape_html(tip)}")

    return "\n".join(lines)


async def send_lesson(bot: Bot, user_id: int, text: str) -> bool:
    """Отправить урок частями если длинный (лимит Telegram 4096)."""
    try:
        chunk_size = 3800
        if len(text) <= chunk_size:
            await bot.send_message(user_id, text, reply_markup=lesson_actions_keyboard())
        else:
            parts = []
            current = ""
            for line in text.split("\n"):
                if len(current) + len(line) + 1 > chunk_size:
                    parts.append(current)
                    current = line
                else:
                    current = f"{current}\n{line}" if current else line
            if current:
                parts.append(current)
            for i, part in enumerate(parts):
                markup = lesson_actions_keyboard() if i == len(parts) - 1 else None
                await bot.send_message(user_id, part, reply_markup=markup)
        return True
    except TelegramForbiddenError:
        logger.warning("User %s blocked bot", user_id)
        return False
    except TelegramBadRequest as e:
        logger.error("Lesson send error %s: %s", user_id, e)
        return False


async def deliver_morning_lesson(bot: Bot, user_id: int, word_count: int = 2) -> bool:
    text = await build_morning_lesson(user_id, word_count)
    if not text:
        return False
    ok = await send_lesson(bot, user_id, text)
    if ok:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        await db_execute(
            "UPDATE users SET last_morning_lesson=?, lesson_counter=COALESCE(lesson_counter,0)+1 WHERE user_id=?",
            (today, user_id),
        )
        await db_execute(
            "INSERT INTO activity_log(user_id, action, xp) VALUES (?, 'morning_lesson', 10)",
            (user_id,),
        )
    return ok


async def deliver_evening_lesson(bot: Bot, user_id: int) -> bool:
    text = await build_evening_lesson(user_id)
    if not text:
        return False
    ok = await send_lesson(bot, user_id, text)
    if ok:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        await db_execute(
            "UPDATE users SET last_evening_lesson=? WHERE user_id=?",
            (today, user_id),
        )
        await db_execute(
            "INSERT INTO activity_log(user_id, action, xp) VALUES (?, 'evening_lesson', 10)",
            (user_id,),
        )
    return ok


def user_local_now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone or "Europe/Moscow"))
    except Exception:
        return datetime.now(ZoneInfo("Europe/Moscow"))
