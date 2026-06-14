"""Чтение: адаптированные новости + comprehension."""

import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api.gemini import generate_text
from api.news import get_latest_news
from services.user import add_xp, get_user_level
from utils.text_utils import escape_html, parse_json_safe

logger = logging.getLogger(__name__)
router = Router()

READING_PROMPT = """Адаптируй новость для уровня {level} английского.

Исходная новость:
{news}

1. Перепиши текст проще (сохрани факты), 120-180 слов
2. Добавь 3 вопроса на понимание с 4 вариантами

JSON:
{{
  "title": "заголовок",
  "text": "адаптированный текст",
  "vocabulary": ["слово1", "слово2", "слово3"],
  "questions": [
    {{"question": "...", "options": ["A","B","C","D"], "correct": 0}}
  ]
}}

correct — индекс 0-3. Только JSON."""

_reading_sessions: dict[int, dict] = {}


@router.message(Command("read"))
async def cmd_read(message: types.Message) -> None:
    user_id = message.from_user.id
    level = await get_user_level(user_id)

    loading = await message.answer("📰 Ищу свежую новость...")

    news = await get_latest_news()
    if not news:
        await loading.edit_text(
            "❌ Новости временно недоступны.\n"
            "RSS-ленты недоступны — попробуй позже."
        )
        return

    await loading.edit_text("✍️ Адаптирую под твой уровень...")

    raw = await generate_text(
        READING_PROMPT.format(level=level, news=news[:1500]),
        user_id=user_id,
        temperature=0.5,
    )
    data = parse_json_safe(raw, {})

    title = data.get("title", "Today's News")
    text = data.get("text", "")
    vocab = data.get("vocabulary", [])
    questions = data.get("questions", [])

    if not text:
        await loading.edit_text("❌ Не удалось адаптировать новость.")
        return

    vocab_line = ""
    if vocab:
        vocab_line = f"\n\n📚 <b>Ключевые слова:</b> {', '.join(escape_html(v) for v in vocab[:5])}"

    await loading.edit_text(
        f"📰 <b>{escape_html(title)}</b>\n"
        f"<i>Уровень: {level}</i>\n\n"
        f"{escape_html(text)}"
        f"{vocab_line}\n\n"
        "Ответь на вопросы ниже 👇"
    )

    if questions:
        _reading_sessions[user_id] = {"questions": questions, "index": 0, "score": 0}
        await _send_question(message, user_id)
    else:
        await add_xp(user_id, "reading")


async def _send_question(message: types.Message, user_id: int) -> None:
    session = _reading_sessions.get(user_id)
    if not session:
        return

    idx = session["index"]
    questions = session["questions"]
    if idx >= len(questions):
        await _finish(message, user_id)
        return

    q = questions[idx]
    options = q.get("options", [])
    correct = q.get("correct", 0)

    buttons = [
        [InlineKeyboardButton(
            text=opt,
            callback_data=f"read:{user_id}:{idx}:{correct}:{i}",
        )]
        for i, opt in enumerate(options)
    ]

    await message.answer(
        f"❓ <b>{idx + 1}/{len(questions)}</b>\n{escape_html(q.get('question', ''))}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("read:"))
async def callback_reading(callback: types.CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Ошибка.")
        return

    _, uid_str, idx_str, correct_str, chosen_str = parts
    user_id = int(uid_str)
    correct = int(correct_str)
    chosen = int(chosen_str)

    if callback.from_user.id != user_id:
        await callback.answer("Не твоё!")
        return

    session = _reading_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия истекла. /read")
        return

    if chosen == correct:
        session["score"] += 1
        feedback = "✅ <b>Верно!</b>"
    else:
        opt = session["questions"][int(idx_str)]["options"][correct]
        feedback = f"❌ Правильно: <i>{escape_html(opt)}</i>"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(feedback)
    await callback.answer()

    session["index"] += 1
    if session["index"] >= len(session["questions"]):
        await _finish(callback.message, user_id)
    else:
        await _send_question(callback.message, user_id)


async def _finish(message: types.Message, user_id: int) -> None:
    session = _reading_sessions.pop(user_id, None)
    if not session:
        return

    total = len(session["questions"])
    pct = round(session["score"] / total * 100) if total else 0
    xp = await add_xp(user_id, "reading")

    await message.answer(
        f"📰 <b>Чтение завершено!</b> {session['score']}/{total} ({pct}%)\n⭐ +{xp} XP"
    )
