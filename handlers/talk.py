"""Разговорная практика с AI."""

import logging

from aiogram import F, Router, types
from aiogram.filters import Command

from api.gemini import generate_text
from api.groq_whisper import transcribe_audio
from config import settings
from keyboards.common import talk_topics_keyboard
from services.sessions import TalkSession, sessions
from services.user import add_xp, get_user_level
from utils.text_utils import escape_html

logger = logging.getLogger(__name__)
router = Router()

TALK_SYSTEM = """You are a friendly English conversation partner and tutor.
Topic: {topic}. Student level: {level}.

Rules:
- Speak mostly in English appropriate for {level} level
- After your English reply, add a brief Russian hint/explanation in parentheses
- Ask follow-up questions to keep the conversation going
- Gently correct major mistakes
- Keep responses under 80 words"""

TOPIC_LABELS = {
    "travel": "Travel & adventures",
    "work": "Work & career",
    "movies": "Movies & entertainment",
    "food": "Food & cooking",
    "technology": "Technology",
    "health": "Health & fitness",
    "random": "Free conversation",
}


@router.message(Command("talk"))
async def cmd_talk(message: types.Message) -> None:
    if sessions.in_talk(message.from_user.id):
        await message.answer("💬 Диалог уже идёт. /stop_talk чтобы завершить.")
        return

    await message.answer(
        "💬 <b>Разговорная практика</b>\n\nВыбери тему:",
        reply_markup=talk_topics_keyboard(),
    )


@router.message(Command("stop_talk"))
async def cmd_stop_talk(message: types.Message) -> None:
    user_id = message.from_user.id
    if user_id in sessions.talk:
        topic = sessions.talk[user_id].topic
        sessions.talk.pop(user_id)
        await message.answer(f"👋 Диалог на тему «{topic}» завершён. Отличная работа!")
    else:
        await message.answer("Нет активного диалога. Начни: /talk")


@router.callback_query(lambda c: c.data and c.data.startswith("talk_topic:"))
async def callback_talk_topic(callback: types.CallbackQuery) -> None:
    topic_key = callback.data.split(":")[1]
    user_id = callback.from_user.id
    level = await get_user_level(user_id)
    topic_label = TOPIC_LABELS.get(topic_key, topic_key)

    sessions.talk[user_id] = TalkSession(topic=topic_label)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    loading = await callback.message.answer("💬 Начинаю диалог...")

    opener = await generate_text(
        f"Start a conversation about {topic_label}. Greet the student and ask an engaging first question.",
        user_id=user_id,
        system=TALK_SYSTEM.format(topic=topic_label, level=level),
        temperature=0.8,
    )

    sessions.talk[user_id].history.append({"role": "assistant", "content": opener})
    await loading.edit_text(f"💬 <b>{topic_label}</b>\n\n{escape_html(opener)}\n\n<i>Отвечай текстом или голосом!</i>")


@router.message(
    lambda m: m.from_user and m.from_user.id in sessions.talk and m.text and not m.text.startswith("/")
)
async def handle_talk_message(message: types.Message) -> None:
    await _process_talk_reply(message, message.text.strip())


@router.message(F.voice, lambda m: m.from_user and m.from_user.id in sessions.talk)
async def handle_talk_voice(message: types.Message) -> None:
    user_id = message.from_user.id

    processing = await message.answer("🎤 Слушаю...")
    try:
        bot_file = await message.bot.get_file(message.voice.file_id)
        file_io = await message.bot.download_file(bot_file.file_path)
        audio_bytes = file_io.read()
    except Exception as e:
        logger.exception(f"Voice download: {e}")
        await processing.edit_text("❌ Ошибка загрузки.")
        return

    text = await transcribe_audio(audio_bytes, "voice.ogg")
    if not text:
        await processing.edit_text("❌ Не удалось распознать. Попробуй текстом.")
        return

    await processing.edit_text(f"📝 <i>{escape_html(text)}</i>")
    await _process_talk_reply(message, text)


async def _process_talk_reply(message: types.Message, user_text: str) -> None:
    user_id = message.from_user.id
    session = sessions.talk.get(user_id)
    if not session:
        return

    level = await get_user_level(user_id)
    session.history.append({"role": "user", "content": user_text})

    # Собираем контекст из истории
    history_text = ""
    for msg in session.history[-settings.TALK_HISTORY_SIZE:]:
        role = "Student" if msg["role"] == "user" else "Tutor"
        history_text += f"{role}: {msg['content']}\n"

    prompt = f"Continue this conversation:\n{history_text}\nRespond as the tutor."

    reply = await generate_text(
        prompt,
        user_id=user_id,
        system=TALK_SYSTEM.format(topic=session.topic, level=level),
        temperature=0.8,
    )

    session.history.append({"role": "assistant", "content": reply})
    xp = await add_xp(user_id, "talk_message")

    await message.answer(f"💬 {escape_html(reply)}\n\n⭐ +{xp} XP")


async def handle_voice_in_talk(message: types.Message, transcribed: str) -> None:
    """Legacy hook — больше не нужен, talk обрабатывает voice сам."""
    pass
