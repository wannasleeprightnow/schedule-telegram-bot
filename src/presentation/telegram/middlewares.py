from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: set[int]):
        self.allowed_ids = allowed_ids

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user and user.id not in self.allowed_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("У вас нет доступа к этому боту.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("У вас нет доступа к этому боту.")
            return None
        return await handler(event, data)
