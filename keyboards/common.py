"""Клавиатуры Telegram."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

TALK_TOPICS = [
    ("🌍 Travel", "travel"),
    ("💼 Work", "work"),
    ("🎬 Movies", "movies"),
    ("🍳 Food", "food"),
    ("💻 Technology", "technology"),
    ("🏃 Health", "health"),
    ("🎲 Random", "random"),
]


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📖 Слово"), KeyboardButton(text="🔁 Повторить")],
            [KeyboardButton(text="🎧 Аудирование"), KeyboardButton(text="📰 Читать")],
            [KeyboardButton(text="💬 Разговор"), KeyboardButton(text="✍️ Грамматика")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def level_keyboard(prefix: str = "level") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=lv, callback_data=f"{prefix}:{lv}") for lv in CEFR_LEVELS[:3]],
        [InlineKeyboardButton(text=lv, callback_data=f"{prefix}:{lv}") for lv in CEFR_LEVELS[3:]],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def talk_topics_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label, topic in TALK_TOPICS:
        row.append(InlineKeyboardButton(text=label, callback_data=f"talk_topic:{topic}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def word_actions(word_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔊 Произнести", callback_data=f"speak_word:{word_id}"),
                InlineKeyboardButton(text="✅ В словаре", callback_data=f"saved_word:{word_id}"),
            ]
        ]
    )
