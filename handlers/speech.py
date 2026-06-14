"""Произношение: Edge TTS + Groq Whisper + AI feedback."""

import logging
import os

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from api.gemini import generate_text
from api.groq_whisper import transcribe_audio
from services.sessions import sessions
from services.user import add_xp
from utils.text_utils import escape_html
from utils.tts import tts_to_voice_file

logger = logging.getLogger(__name__)
router = Router()

PRONUNCIATION_PROMPT = """Ты — преподаватель английского. Сравни эталон и распознанную речь.

Эталон: "{expected}"
Распознано: "{actual}"

Если совпадает — похвали. Если нет — укажи конкретные ошибки в звуках.
Дай 2-3 совета. Кратко, на русском, до 5 предложений."""


@router.message(Command("speak"))
async def cmd_speak(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Пример: <code>/speak How are you doing?</code>")
        return

    phrase = parts[1].strip()
    await message.answer(f"🔊 Озвучиваю: <i>{escape_html(phrase)}</i>")

    tmp_path = await tts_to_voice_file(phrase)
    if not tmp_path:
        await message.answer("❌ Не удалось сгенерировать аудио.")
        return

    try:
        await message.answer_voice(
            FSInputFile(tmp_path),
            caption=f"🗣️ Повтори эту фразу голосом!",
        )
        sessions.expected_phrases[message.from_user.id] = phrase
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.message(F.voice | F.audio)
async def handle_voice(message: types.Message) -> None:
    user_id = message.from_user.id

    # В режиме talk — обрабатывается там
    if sessions.in_talk(user_id):
        return

    processing = await message.answer("🎤 Распознаю речь...")

    try:
        file_obj = message.voice or message.audio
        filename = "voice.ogg" if message.voice else (file_obj.file_name or "audio.mp3")
        bot_file = await message.bot.get_file(file_obj.file_id)
        file_io = await message.bot.download_file(bot_file.file_path)
        audio_bytes = file_io.read()
    except Exception as e:
        logger.exception(f"Download error: {e}")
        await processing.edit_text("❌ Не удалось скачать аудио.")
        return

    transcribed = await transcribe_audio(audio_bytes, filename)
    if not transcribed:
        await processing.edit_text(
            "❌ Не удалось распознать речь.\n"
            "Нужен <b>GROQ_API_KEY</b> (бесплатный на console.groq.com)."
        )
        return

    expected = sessions.expected_phrases.pop(user_id, None)

    if expected:
        analysis = await generate_text(
            PRONUNCIATION_PROMPT.format(expected=expected, actual=transcribed),
            user_id=user_id,
        )
        xp = await add_xp(user_id, "pronunciation")
        await processing.edit_text(
            f"📝 <b>Распознано:</b> <i>{escape_html(transcribed)}</i>\n"
            f"🎯 <b>Эталон:</b> <i>{escape_html(expected)}</i>\n\n"
            f"📊 {escape_html(analysis)}\n\n⭐ +{xp} XP"
        )
    else:
        await processing.edit_text(
            f"📝 <b>Распознано:</b>\n<i>{escape_html(transcribed)}</i>\n\n"
            "💡 Для проверки произношения: /speak &lt;фраза&gt;, затем повтори голосом."
        )
