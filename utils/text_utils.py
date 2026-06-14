"""Вспомогательные утилиты для работы с текстом."""

import json
import random
import re
from typing import List, Optional


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def parse_json_safe(text: str, default=None):
    text = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def format_word_card(
    word: str,
    translation: str,
    examples: List[dict],
    level: str,
    synonyms: List[str],
    antonyms: List[str],
    etymology: str = "",
) -> str:
    lines = [
        f"📖 <b>{escape_html(word)}</b>",
        f"🇷🇺 <b>Перевод:</b> {escape_html(translation)}",
        f"📊 <b>Уровень:</b> {escape_html(level)}",
        "",
    ]

    if etymology:
        lines += [f"💡 <b>Мнемоника:</b> {escape_html(etymology)}", ""]

    if examples:
        lines.append("📝 <b>Примеры:</b>")
        for i, ex in enumerate(examples[:3], 1):
            en = escape_html(ex.get("en", ""))
            ru = escape_html(ex.get("ru", ""))
            lines.append(f"  {i}. <i>{en}</i>")
            lines.append(f"     🇷🇺 {ru}")
        lines.append("")

    if synonyms:
        lines.append(f"✅ <b>Синонимы:</b> {', '.join(escape_html(s) for s in synonyms[:5])}")
    if antonyms:
        lines.append(f"❌ <b>Антонимы:</b> {', '.join(escape_html(a) for a in antonyms[:5])}")

    return "\n".join(lines)


def build_quiz_options(correct: str, all_words: List[str], count: int = 4) -> List[str]:
    distractors = [w for w in all_words if w != correct]
    if len(distractors) >= count - 1:
        chosen = random.sample(distractors, count - 1)
    else:
        chosen = distractors + ["unknown", "mistake", "error"][: count - 1 - len(distractors)]
    options = [correct] + chosen[: count - 1]
    random.shuffle(options)
    return options


def clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()
