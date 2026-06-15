"""
Инициализация SQLite базы данных и вспомогательные функции.
"""

import asyncio
import logging
import os
import sqlite3
from typing import List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

_db_lock = asyncio.Lock()


def _ensure_db_dir() -> None:
    db_dir = os.path.dirname(os.path.abspath(settings.DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(settings.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db() -> None:
    async with _db_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _create_tables)
    logger.info("Таблицы БД проверены/созданы.")


def _create_tables() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id        INTEGER PRIMARY KEY,
                username       TEXT,
                language       TEXT    DEFAULT 'en',
                level          TEXT    DEFAULT 'A2',
                timezone       TEXT    DEFAULT 'Europe/Moscow',
                morning_window TEXT    DEFAULT '08:00-10:00',
                evening_window TEXT    DEFAULT '18:00-20:00',
                streak_days    INTEGER DEFAULT 0,
                total_xp       INTEGER DEFAULT 0,
                last_activity  TIMESTAMP,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS vocabulary (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                word        TEXT    NOT NULL,
                translation TEXT,
                examples    TEXT,
                level       TEXT,
                synonyms    TEXT,
                antonyms    TEXT,
                next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interval    INTEGER DEFAULT 0,
                ease_factor REAL    DEFAULT 2.5,
                repetitions INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS review_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                word_id   INTEGER NOT NULL,
                quality   INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(word_id) REFERENCES vocabulary(id)
            );

            CREATE TABLE IF NOT EXISTS news_cache (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT,
                content    TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                data       TEXT,
                expires_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                action     TEXT NOT NULL,
                xp         INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );
        """)
        _migrate_users(conn)
    conn.close()


def _migrate_users(conn: sqlite3.Connection) -> None:
    """Добавить новые колонки в существующую БД."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    migrations = [
        ("streak_days", "INTEGER DEFAULT 0"),
        ("total_xp", "INTEGER DEFAULT 0"),
        ("last_activity", "TIMESTAMP"),
    ]
    for name, typedef in migrations:
        if name not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")


async def db_execute(query: str, params: Tuple = ()) -> None:
    async with _db_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _execute, query, params)


async def db_fetchone(query: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    async with _db_lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fetchone, query, params)


async def db_fetchall(query: str, params: Tuple = ()) -> List[sqlite3.Row]:
    async with _db_lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fetchall, query, params)


async def db_lastrowid(query: str, params: Tuple = ()) -> int:
    async with _db_lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _lastrowid, query, params)


def _execute(query: str, params: Tuple) -> None:
    conn = get_connection()
    with conn:
        conn.execute(query, params)
    conn.close()


def _fetchone(query: str, params: Tuple) -> Optional[sqlite3.Row]:
    conn = get_connection()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row


def _fetchall(query: str, params: Tuple) -> List[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def _lastrowid(query: str, params: Tuple) -> int:
    conn = get_connection()
    with conn:
        cur = conn.execute(query, params)
        rowid = cur.lastrowid
    conn.close()
    return rowid
