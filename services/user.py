"""
Операции с пользователями: регистрация, XP, streak.
"""

import logging
from datetime import date, datetime
from typing import Optional

from database import db_execute, db_fetchone

logger = logging.getLogger(__name__)

XP_REWARDS = {
    "word": 5,
    "review_correct": 3,
    "review_session": 10,
    "listening_correct": 4,
    "listening_session": 15,
    "reading": 20,
    "grammar": 8,
    "talk_message": 2,
    "pronunciation": 6,
}


async def ensure_user(user_id: int, username: Optional[str] = None) -> None:
    existing = await db_fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not existing:
        await db_execute(
            "INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)",
            (user_id, username or ""),
        )


async def get_user_level(user_id: int) -> str:
    row = await db_fetchone("SELECT level FROM users WHERE user_id=?", (user_id,))
    return row["level"] if row else "A2"


async def set_user_level(user_id: int, level: str) -> None:
    await db_execute("UPDATE users SET level=? WHERE user_id=?", (level, user_id))


async def add_xp(user_id: int, action: str, amount: Optional[int] = None) -> int:
    """Начислить XP и обновить streak. Возвращает начисленное количество."""
    xp = amount if amount is not None else XP_REWARDS.get(action, 0)
    if xp <= 0:
        return 0

    await _update_streak(user_id)
    await db_execute(
        "UPDATE users SET total_xp = total_xp + ?, last_activity = CURRENT_TIMESTAMP WHERE user_id=?",
        (xp, user_id),
    )
    await db_execute(
        "INSERT INTO activity_log(user_id, action, xp) VALUES (?, ?, ?)",
        (user_id, action, xp),
    )
    return xp


async def _update_streak(user_id: int) -> None:
    row = await db_fetchone(
        "SELECT streak_days, last_activity FROM users WHERE user_id=?", (user_id,)
    )
    if not row:
        return

    today = date.today()
    last = row["last_activity"]
    streak = row["streak_days"] or 0

    if last:
        try:
            last_date = datetime.fromisoformat(str(last)).date()
        except ValueError:
            last_date = None
    else:
        last_date = None

    if last_date == today:
        return
    if last_date and (today - last_date).days == 1:
        streak += 1
    elif last_date != today:
        streak = 1

    await db_execute(
        "UPDATE users SET streak_days=?, last_activity=CURRENT_TIMESTAMP WHERE user_id=?",
        (streak, user_id),
    )


async def get_user_stats(user_id: int) -> dict:
    user = await db_fetchone(
        "SELECT username, level, streak_days, total_xp, created_at FROM users WHERE user_id=?",
        (user_id,),
    )
    vocab_count = await db_fetchone(
        "SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=?", (user_id,)
    )
    due_count = await db_fetchone(
        "SELECT COUNT(*) as cnt FROM vocabulary WHERE user_id=? AND next_review <= CURRENT_TIMESTAMP",
        (user_id,),
    )
    reviews = await db_fetchone(
        "SELECT COUNT(*) as cnt FROM review_log WHERE user_id=?", (user_id,)
    )
    week_xp = await db_fetchone(
        """SELECT COALESCE(SUM(xp), 0) as xp FROM activity_log
           WHERE user_id=? AND created_at >= datetime('now', '-7 days')""",
        (user_id,),
    )

    return {
        "username": user["username"] if user else "",
        "level": user["level"] if user else "A2",
        "streak": user["streak_days"] if user else 0,
        "total_xp": user["total_xp"] if user else 0,
        "vocab_count": vocab_count["cnt"] if vocab_count else 0,
        "due_count": due_count["cnt"] if due_count else 0,
        "reviews_total": reviews["cnt"] if reviews else 0,
        "week_xp": week_xp["xp"] if week_xp else 0,
        "member_since": user["created_at"] if user else "",
    }
