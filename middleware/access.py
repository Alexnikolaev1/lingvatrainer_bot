"""Проверка доступа: только разрешённые Telegram user ID."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from config import settings

logger = logging.getLogger(__name__)


def _get_user(event: TelegramObject) -> Optional[User]:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return None


class AccessControlMiddleware(BaseMiddleware):
    """
    Если задан ALLOWED_USER_IDS — бот отвечает только этим пользователям.
    Пустая переменная = доступ для всех (как раньше).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        allowed: Optional[Set[int]] = settings.allowed_user_ids
        if allowed is None:
            return await handler(event, data)

        user = _get_user(event)
        if not user or user.id in allowed:
            return await handler(event, data)

        # Помочь узнать свой ID для настройки ALLOWED_USER_IDS
        if isinstance(event, Message) and event.text:
            cmd = event.text.strip().split()[0].split("@")[0].lower()
            if cmd in ("/myid", "/id"):
                return await handler(event, data)

        logger.warning("Доступ запрещён: user_id=%s username=%s", user.id, user.username)

        if isinstance(event, Message):
            await event.answer(
                "🔒 <b>Этот бот приватный.</b>\n"
                f"Ваш ID: <code>{user.id}</code>"
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("🔒 Нет доступа", show_alert=True)

        return None
