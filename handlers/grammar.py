"""Грамматика: проверка предложений и drill-упражнения."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from api.gemini import generate_text
from services.sessions import sessions
from services.user import add_xp
from utils.text_utils import escape_html

logger = logging.getLogger(__name__)
router = Router()

GRAMMAR_CHECK_PROMPT = """Проверь предложение на английском и исправь ошибки.

Предложение: "{sentence}"
Уровень ученика: {level}

Формат ответа:
1. ✅/❌ Оценка
2. Исправленный вариант (если нужно)
3. Объяснение ошибок по-русски (кратко)
4. Правило грамматики одним предложением"""

GRAMMAR_DRILL_PROMPT = """Создай мини-упражнение по теме "{topic}" для уровня {level}.

Формат:
📝 <b>Задание:</b> (1-2 предложения с пропуском ___)
💡 <b>Подсказка:</b> (грамматическое правило)
✅ <b>Ответ:</b> (правильный вариант)

HTML-разметка для Telegram. На русском, кроме английских примеров."""


@router.message(Command("grammar"))
async def cmd_grammar(message: types.Message) -> None:
    sessions.grammar_pending.add(message.from_user.id)
    await message.answer(
        "✍️ <b>Грамматика</b>\n\n"
        "Отправь предложение на английском — проверю и объясню ошибки.\n\n"
        "Или: <code>/grammar_drill Present Perfect</code>"
    )


@router.message(Command("grammar_drill"))
async def cmd_grammar_drill(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    topic = parts[1].strip() if len(parts) > 1 else "mixed tenses"

    from services.user import get_user_level
    level = await get_user_level(message.from_user.id)

    loading = await message.answer(f"📝 Готовлю упражнение: <b>{escape_html(topic)}</b>...")

    result = await generate_text(
        GRAMMAR_DRILL_PROMPT.format(topic=topic, level=level),
        user_id=message.from_user.id,
    )
    xp = await add_xp(message.from_user.id, "grammar")
    await loading.edit_text(f"{result}\n\n⭐ +{xp} XP")


@router.message(
    lambda m: m.from_user
    and m.from_user.id in sessions.grammar_pending
    and m.text
    and not m.text.startswith("/")
)
async def handle_grammar_sentence(message: types.Message) -> None:
    user_id = message.from_user.id
    sessions.grammar_pending.discard(user_id)

    from services.user import get_user_level
    level = await get_user_level(user_id)
    sentence = message.text.strip()

    loading = await message.answer("🔍 Проверяю...")

    result = await generate_text(
        GRAMMAR_CHECK_PROMPT.format(sentence=sentence, level=level),
        user_id=user_id,
        temperature=0.3,
    )
    xp = await add_xp(user_id, "grammar")
    await loading.edit_text(f"{escape_html(result)}\n\n⭐ +{xp} XP")
