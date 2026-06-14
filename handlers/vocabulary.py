"""Словарь: разбор слов, сохранение, SRS."""

import asyncio
import json
import logging
import os
import re

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from api.datamuse import get_antonyms, get_synonyms
from api.gemini import generate_text
from database import db_execute, db_fetchall, db_fetchone, db_lastrowid
from keyboards.common import word_actions
from services.sessions import sessions
from services.user import add_xp, ensure_user
from utils.text_utils import escape_html, format_word_card, parse_json_safe
from utils.tts import tts_to_voice_file

logger = logging.getLogger(__name__)
router = Router()

WORD_PROMPT = """Ты — эксперт-преподаватель английского. Разбери "{word}" и ответь СТРОГО JSON:

{{
  "translation": "перевод на русский",
  "level": "CEFR (A1/A2/B1/B2/C1/C2)",
  "etymology": "мнемоника или этимология (1-2 предложения по-русски)",
  "examples": [
    {{"en": "пример 1", "ru": "перевод 1"}},
    {{"en": "пример 2", "ru": "перевод 2"}},
    {{"en": "пример 3", "ru": "перевод 3"}}
  ]
}}

Только JSON, без markdown."""


async def process_word(word: str, user_id: int) -> dict:
    word = word.strip().lower()
    gemini_task = asyncio.create_task(
        generate_text(WORD_PROMPT.format(word=word), user_id=user_id, temperature=0.3)
    )
    syn_task = asyncio.create_task(get_synonyms(word))
    ant_task = asyncio.create_task(get_antonyms(word))

    gemini_raw, synonyms, antonyms = await asyncio.gather(gemini_task, syn_task, ant_task)
    data = parse_json_safe(gemini_raw, {})

    return {
        "translation": data.get("translation", "нет данных"),
        "level": data.get("level", "?"),
        "etymology": data.get("etymology", ""),
        "examples": data.get("examples", []),
        "synonyms": synonyms,
        "antonyms": antonyms,
    }


async def save_word(user_id: int, word: str, info: dict) -> int:
    existing = await db_fetchone(
        "SELECT id FROM vocabulary WHERE user_id=? AND LOWER(word)=LOWER(?)",
        (user_id, word),
    )
    examples_json = json.dumps(info["examples"], ensure_ascii=False)
    synonyms_json = json.dumps(info["synonyms"], ensure_ascii=False)
    antonyms_json = json.dumps(info["antonyms"], ensure_ascii=False)

    if existing:
        await db_execute(
            """UPDATE vocabulary SET translation=?, examples=?, level=?, synonyms=?, antonyms=?
               WHERE id=?""",
            (info["translation"], examples_json, info["level"],
             synonyms_json, antonyms_json, existing["id"]),
        )
        return existing["id"]

    return await db_lastrowid(
        """INSERT INTO vocabulary
           (user_id, word, translation, examples, level, synonyms, antonyms, next_review)
           VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (user_id, word, info["translation"], examples_json, info["level"],
         synonyms_json, antonyms_json),
    )


@router.message(Command("word"))
async def cmd_word(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи слово: <code>/word serendipity</code>")
        return
    await _handle_word_lookup(message, parts[1].strip())


@router.message(
    lambda m: (
        m.text
        and not m.text.startswith("/")
        and len(m.text.split()) <= 4
        and m.text[0].isalpha()
        and all(c.isalpha() or c in " '-" for c in m.text)
    )
)
async def handle_plain_word(message: types.Message) -> None:
    if sessions.is_busy(message.from_user.id):
        return
    text = message.text.strip()
    if re.match(r"^[a-zA-Z][a-zA-Z '\-]{0,40}$", text):
        await _handle_word_lookup(message, text)


async def _handle_word_lookup(message: types.Message, word: str) -> None:
    user_id = message.from_user.id
    await ensure_user(user_id, message.from_user.username)

    loading = await message.answer(f"🔍 Разбираю <b>{escape_html(word)}</b>...")

    try:
        info = await process_word(word, user_id)
        word_id = await save_word(user_id, word, info)
        xp = await add_xp(user_id, "word")

        card = format_word_card(
            word=word,
            translation=info["translation"],
            examples=info["examples"],
            level=info["level"],
            synonyms=info["synonyms"],
            antonyms=info["antonyms"],
            etymology=info["etymology"],
        )
        card += f"\n\n⭐ +{xp} XP"

        await loading.delete()
        await message.answer(card, reply_markup=word_actions(word_id))
    except Exception as e:
        logger.exception(f"Word lookup error: {e}")
        await loading.edit_text("❌ Не удалось разобрать слово. Попробуй позже.")


@router.callback_query(lambda c: c.data and c.data.startswith("speak_word:"))
async def callback_speak_word(callback: types.CallbackQuery) -> None:
    word_id = int(callback.data.split(":")[1])
    row = await db_fetchone("SELECT word FROM vocabulary WHERE id=?", (word_id,))
    if not row:
        await callback.answer("Слово не найдено.")
        return

    await callback.answer()
    tmp_path = await tts_to_voice_file(row["word"])
    if tmp_path:
        try:
            await callback.message.answer_voice(FSInputFile(tmp_path))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    else:
        await callback.message.answer("❌ Не удалось озвучить.")


@router.callback_query(lambda c: c.data and c.data.startswith("saved_word:"))
async def callback_saved_word(callback: types.CallbackQuery) -> None:
    await callback.answer("✅ Слово в словаре!")


@router.message(Command("vocab"))
async def cmd_vocab(message: types.Message) -> None:
    user_id = message.from_user.id
    words = await db_fetchall(
        """SELECT word, translation, level FROM vocabulary
           WHERE user_id=? ORDER BY id DESC LIMIT 15""",
        (user_id,),
    )
    if not words:
        await message.answer("📭 Словарь пуст. Отправь английское слово!")
        return

    lines = ["📚 <b>Твой словарь (последние 15):</b>\n"]
    for w in words:
        lines.append(
            f"• <b>{escape_html(w['word'])}</b> — {escape_html(w['translation'])} "
            f"<i>({w['level']})</i>"
        )

    total = await db_fetchone("SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=?", (user_id,))
    lines.append(f"\n📊 Всего: <b>{total['cnt']}</b> слов")
    await message.answer("\n".join(lines))
