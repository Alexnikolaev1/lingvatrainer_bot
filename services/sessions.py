"""
Централизованное хранение активных сессий пользователей (in-memory).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TalkSession:
    topic: str
    history: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ListeningSession:
    questions: List[dict]
    index: int = 0
    score: int = 0
    text: str = ""


@dataclass
class QuizSession:
    words: List[dict]
    index: int = 0
    score: int = 0
    all_translations: List[str] = field(default_factory=list)


class SessionStore:
    """Единое хранилище сессий — избегаем разрозненных глобальных dict."""

    def __init__(self) -> None:
        self.talk: Dict[int, TalkSession] = {}
        self.listening: Dict[int, ListeningSession] = {}
        self.quiz: Dict[int, QuizSession] = {}
        self.expected_phrases: Dict[int, str] = {}
        self.grammar_pending: set[int] = set()

    def is_busy(self, user_id: int) -> bool:
        return (
            user_id in self.talk
            or user_id in self.listening
            or user_id in self.quiz
            or user_id in self.grammar_pending
        )

    def in_talk(self, user_id: int) -> bool:
        return user_id in self.talk


sessions = SessionStore()
