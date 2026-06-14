"""Middleware LINGVA.AI."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from services.user import ensure_user


class UserMiddleware(BaseMiddleware):
    """Автоматическая регистрация пользователя при любом сообщении."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            await ensure_user(event.from_user.id, event.from_user.username)
        return await handler(event, data)
