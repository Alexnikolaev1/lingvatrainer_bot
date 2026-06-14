"""SRS-повторения слов (SM-2)."""

import logging
import random

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import settings
from database import db_execute, db_fetchall, db_fetchone
from services.sessions import QuizSession, sessions
from services.user import add_xp
from srs import next_review_date, quality_from_button, sm2_update
from utils.text_utils import escape_html

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("review_now", "review"))
async def cmd_review_now(message: types.Message) -> None:
    await start_review_session(message, message.from_user.id)


@router.message(lambda m: m.text and m.text.strip() == "🔁 Повторить")
async def menu_review(message: types.Message) -> None:
    await start_review_session(message, message.from_user.id)


async def start_review_session(message: types.Message, user_id: int) -> None:
    due_words = await db_fetchall(
        """SELECT id, word, translation FROM vocabulary
           WHERE user_id=? AND next_review <= CURRENT_TIMESTAMP
           ORDER BY next_review ASC LIMIT ?""",
        (user_id, settings.QUIZ_SIZE),
    )

    if not due_words:
        await message.answer(
            "🎉 Нет слов для повторения!\n"
            "Добавь новые слова или вернись позже."
        )
        return

    all_translations = await db_fetchall(
        "SELECT translation FROM vocabulary WHERE user_id=?", (user_id,)
    )
    all_tr = [r["translation"] for r in all_translations if r["translation"]]

    quiz_words = [dict(w) for w in due_words]
    random.shuffle(quiz_words)

    sessions.quiz[user_id] = QuizSession(
        words=quiz_words,
        all_translations=all_tr,
    )

    await message.answer(
        f"🔁 <b>Повторение</b> — {len(quiz_words)} слов\n\nВыбери правильный перевод:"
    )
    await _send_question(message.bot, message.chat.id, user_id)


async def _send_question(bot, chat_id: int, user_id: int) -> None:
    state = sessions.quiz.get(user_id)
    if not state:
        return

    idx = state.index
    if idx >= len(state.words):
        await _finish(bot, chat_id, user_id)
        return

    current = state.words[idx]
    correct = current["translation"]
    distractors = [t for t in state.all_translations if t != correct]
    wrong = random.sample(distractors, min(3, len(distractors))) if distractors else ["?", "!", "..."]
    options = [correct] + wrong[:3]
    random.shuffle(options)
    correct_idx = options.index(correct)

    buttons = [
        [InlineKeyboardButton(
            text=opt,
            callback_data=f"quiz:{user_id}:{current['id']}:{correct_idx}:{i}",
        )]
        for i, opt in enumerate(options)
    ]

    await bot.send_message(
        chat_id,
        f"❓ {idx + 1}/{len(state.words)}\n\n<b>{escape_html(current['word'])}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("quiz:"))
async def callback_quiz(callback: types.CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Ошибка.")
        return

    _, uid_str, word_id_str, correct_idx_str, chosen_idx_str = parts
    user_id = int(uid_str)
    word_id = int(word_id_str)
    correct_idx = int(correct_idx_str)
    chosen_idx = int(chosen_idx_str)

    if callback.from_user.id != user_id:
        await callback.answer("Это не твой квиз!")
        return

    state = sessions.quiz.get(user_id)
    if not state:
        await callback.answer("Сессия истекла. /review")
        return

    is_correct = chosen_idx == correct_idx
    quality = quality_from_button(is_correct)
    new_interval = 1

    word_row = await db_fetchone(
        "SELECT repetitions, ease_factor, interval FROM vocabulary WHERE id=?",
        (word_id,),
    )
    if word_row:
        new_reps, new_ef, new_interval = sm2_update(
            word_row["repetitions"], word_row["ease_factor"], word_row["interval"], quality
        )
        await db_execute(
            """UPDATE vocabulary SET repetitions=?, ease_factor=?, interval=?, next_review=?
               WHERE id=?""",
            (new_reps, new_ef, new_interval, next_review_date(new_interval).isoformat(), word_id),
        )
        await db_execute(
            "INSERT INTO review_log(user_id, word_id, quality) VALUES (?, ?, ?)",
            (user_id, word_id, quality),
        )

    if is_correct:
        state.score += 1
        await add_xp(user_id, "review_correct")
        feedback = "✅ <b>Верно!</b>"
    else:
        cur = state.words[state.index]
        feedback = f"❌ <b>Неверно.</b> → {escape_html(cur['translation'])}"

    feedback += f"\n<i>Следующее повторение через {new_interval} дн.</i>"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(feedback)
    await callback.answer()

    state.index += 1
    await _send_question(callback.bot, callback.message.chat.id, user_id)


async def _finish(bot, chat_id: int, user_id: int) -> None:
    state = sessions.quiz.pop(user_id, None)
    if not state:
        return

    total = len(state.words)
    score = state.score
    pct = round(score / total * 100) if total else 0
    xp = await add_xp(user_id, "review_session")

    emoji = "🏆" if pct >= 80 else "👍" if pct >= 60 else "💪"
    await bot.send_message(
        chat_id,
        f"{emoji} <b>Готово!</b> {score}/{total} ({pct}%)\n⭐ +{xp} XP",
    )
