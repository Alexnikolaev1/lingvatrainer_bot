"""Команды /start и /help, главное меню."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from database import db_execute, db_fetchone
from keyboards.common import main_menu

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = """
<b>🎓 LINGVA.AI — персональный AI-репетитор английского</b>

<b>📖 Словарь</b>
/word &lt;слово&gt; — разбор слова с примерами и SRS
/vocab — твой словарный запас
<i>Или просто отправь английское слово!</i>

<b>🔁 Повторения (SM-2)</b>
/review — интервальное повторение слов

<b>🎤 Произношение</b>
/speak &lt;фраза&gt; — эталон + проверка голосом
<i>Отправь голосовое — распознаю и дам feedback</i>

<b>🎧 Аудирование</b>
/listening — текст + вопросы на понимание

<b>📰 Чтение</b>
/read — адаптированная новость + comprehension

<b>✍️ Грамматика</b>
/grammar — проверка предложения
/grammar_drill &lt;тема&gt; — мини-упражнение

<b>💬 Разговор</b>
/talk — диалог на выбранную тему
/stop_talk — завершить

<b>👤 Профиль</b>
/stats — прогресс, XP, streak
/settings — уровень CEFR, окна повторений

/help — эта справка
"""


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name

    existing = await db_fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))

    if not existing:
        await db_execute(
            "INSERT INTO users(user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        logger.info(f"Новый пользователь: {user_id}")
        greeting = (
            f"👋 Привет, <b>{username}</b>!\n\n"
            "Я <b>LINGVA.AI</b> — твой AI-репетитор английского.\n\n"
            "🎯 Учу слова с интервальными повторениями, тренирую произношение, "
            "даю новости и веду живой диалог.\n\n"
            "💡 <b>Всё бесплатно</b> — Gemini, Groq, Edge TTS, Datamuse.\n\n"
            "Отправь английское слово или нажми кнопку ниже 👇"
        )
    else:
        greeting = f"👋 С возвращением, <b>{username}</b>!\n\nЧто будем делать?"

    await message.answer(greeting, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("myid", "id"))
async def cmd_myid(message: types.Message) -> None:
    """Показать Telegram user ID (нужен для ALLOWED_USER_IDS)."""
    u = message.from_user
    await message.answer(
        f"🆔 <b>Ваш Telegram ID:</b> <code>{u.id}</code>\n"
        f"👤 Username: @{u.username or '—'}\n\n"
        "Добавьте этот ID в Railway → Variables →\n"
        "<code>ALLOWED_USER_IDS={id}</code>".format(id=u.id)
    )


@router.message(lambda m: m.text and m.text.strip() == "📖 Слово")
async def menu_word(message: types.Message) -> None:
    await message.answer(
        "Отправь английское слово или фразу.\n"
        "Например: <code>serendipity</code> или <code>break the ice</code>"
    )


@router.message(lambda m: m.text and m.text.strip() == "📊 Статистика")
async def menu_stats(message: types.Message) -> None:
    from handlers.stats import cmd_stats
    await cmd_stats(message)


@router.message(lambda m: m.text and m.text.strip() == "⚙️ Настройки")
async def menu_settings(message: types.Message) -> None:
    from handlers.stats import cmd_settings
    await cmd_settings(message)


@router.message(lambda m: m.text and m.text.strip() == "🎧 Аудирование")
async def menu_listening(message: types.Message) -> None:
    from handlers.listening import cmd_listening
    await cmd_listening(message)


@router.message(lambda m: m.text and m.text.strip() == "📰 Читать")
async def menu_reading(message: types.Message) -> None:
    from handlers.reading import cmd_read
    await cmd_read(message)


@router.message(lambda m: m.text and m.text.strip() == "💬 Разговор")
async def menu_talk(message: types.Message) -> None:
    from handlers.talk import cmd_talk
    await cmd_talk(message)


@router.message(lambda m: m.text and m.text.strip() == "✍️ Грамматика")
async def menu_grammar(message: types.Message) -> None:
    from handlers.grammar import cmd_grammar
    await cmd_grammar(message)
