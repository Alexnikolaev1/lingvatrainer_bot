"""Аудирование: TTS + comprehension quiz."""

import logging
import os

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from api.gemini import generate_text
from services.sessions import ListeningSession, sessions
from services.user import add_xp, get_user_level
from utils.text_utils import escape_html, parse_json_safe
from utils.tts import tts_to_voice_file

logger = logging.getLogger(__name__)
router = Router()

LISTENING_PROMPT = """Создай упражнение на аудирование для уровня {level}.

Короткий текст (5-7 предложений) + 3 вопроса с 4 вариантами.

JSON:
{{
  "text": "english text",
  "questions": [
    {{"question": "...", "options": ["A","B","C","D"], "correct": 0}}
  ]
}}

correct — индекс 0-3. Только JSON."""


@router.message(Command("listening"))
async def cmd_listening(message: types.Message) -> None:
    user_id = message.from_user.id
    level = await get_user_level(user_id)

    processing = await message.answer("🎧 Генерирую упражнение...")

    raw = await generate_text(LISTENING_PROMPT.format(level=level), user_id=user_id)
    data = parse_json_safe(raw, {})
    listen_text = data.get("text", "")
    questions = data.get("questions", [])

    if not listen_text or not questions:
        await processing.edit_text("❌ Не удалось создать упражнение. Попробуй позже.")
        return

    await processing.edit_text("🔊 Озвучиваю...")

    tmp_path = await tts_to_voice_file(listen_text)
    if not tmp_path:
        await processing.edit_text("❌ Ошибка TTS.")
        return

    try:
        await message.answer_voice(
            FSInputFile(tmp_path),
            caption=(
                f"🎧 <b>Аудирование</b> ({level})\n\n"
                f"📄 <i>{escape_html(listen_text)}</i>"
            ),
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    sessions.listening[user_id] = ListeningSession(
        questions=questions, text=listen_text
    )
    await processing.delete()
    await _send_question(message.bot, message.chat.id, user_id)


async def _send_question(bot, chat_id: int, user_id: int) -> None:
    session = sessions.listening.get(user_id)
    if not session or session.index >= len(session.questions):
        await _finish(bot, chat_id, user_id)
        return

    q = session.questions[session.index]
    options = q.get("options", [])
    correct = q.get("correct", 0)
    idx = session.index

    buttons = [
        [InlineKeyboardButton(
            text=opt,
            callback_data=f"listen:{user_id}:{idx}:{correct}:{i}",
        )]
        for i, opt in enumerate(options)
    ]

    await bot.send_message(
        chat_id,
        f"❓ <b>{idx + 1}/{len(session.questions)}</b>\n{escape_html(q.get('question', ''))}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("listen:"))
async def callback_listening(callback: types.CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Ошибка.")
        return

    _, uid_str, idx_str, correct_str, chosen_str = parts
    user_id = int(uid_str)
    correct = int(correct_str)
    chosen = int(chosen_str)

    if callback.from_user.id != user_id:
        await callback.answer("Не твоё упражнение!")
        return

    session = sessions.listening.get(user_id)
    if not session:
        await callback.answer("Сессия истекла. /listening")
        return

    if chosen == correct:
        session.score += 1
        await add_xp(user_id, "listening_correct")
        feedback = "✅ <b>Верно!</b>"
    else:
        opt = session.questions[int(idx_str)]["options"][correct]
        feedback = f"❌ Правильно: <i>{escape_html(opt)}</i>"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(feedback)
    await callback.answer()

    session.index += 1
    await _send_question(callback.bot, callback.message.chat.id, user_id)


async def _finish(bot, chat_id: int, user_id: int) -> None:
    session = sessions.listening.pop(user_id, None)
    if not session:
        return

    total = len(session.questions)
    pct = round(session.score / total * 100) if total else 0
    xp = await add_xp(user_id, "listening_session")
    emoji = "🏆" if pct >= 80 else "👍" if pct >= 60 else "💪"

    await bot.send_message(
        chat_id,
        f"{emoji} <b>Результат:</b> {session.score}/{total} ({pct}%)\n⭐ +{xp} XP\n\n/listening — ещё раз",
    )
