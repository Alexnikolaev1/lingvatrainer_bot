"""
Алгоритм интервального повторения SuperMemo SM-2.
"""

from datetime import datetime, timedelta
from typing import Tuple


def sm2_update(
    repetitions: int,
    ease_factor: float,
    interval: int,
    quality: int,
) -> Tuple[int, float, int]:
    if quality < 0 or quality > 5:
        raise ValueError(f"quality должно быть от 0 до 5, получено: {quality}")

    if quality < 3:
        new_repetitions = 0
        new_interval = 1
        new_ease_factor = ease_factor
    else:
        new_repetitions = repetitions + 1
        if new_repetitions == 1:
            new_interval = 1
        elif new_repetitions == 2:
            new_interval = 6
        else:
            new_interval = round(interval * ease_factor)

        new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease_factor = max(1.3, new_ease_factor)

    return new_repetitions, round(new_ease_factor, 4), new_interval


def next_review_date(interval: int) -> datetime:
    return datetime.utcnow() + timedelta(days=interval)


def quality_from_button(answer_correct: bool, hesitation: bool = False) -> int:
    if not answer_correct:
        return 1
    if hesitation:
        return 3
    return 4
