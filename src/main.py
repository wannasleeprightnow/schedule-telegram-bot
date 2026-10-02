import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.application.schedule_service import ScheduleService
from src.application.user_service import UserService
from src.infrastructure.cache.workbook_cache import WorkbookCache
from src.infrastructure.config.settings import Settings
from src.infrastructure.config.user_config import UserConfig
from src.presentation.telegram.handlers.notifications import register_notification_handlers, schedule_user_job
from src.presentation.telegram.handlers.schedule import register_schedule_handlers
from src.presentation.telegram.middlewares import AccessMiddleware


async def main() -> None:
    settings = Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.allowed_user_ids:
        raise RuntimeError("Задайте TELEGRAM_USER_IDS в .env")
    if len(settings.allowed_user_ids) > 5:
        raise RuntimeError("В TELEGRAM_USER_IDS можно указать не более 5 идентификаторов")

    data_dir = Path(settings.data_dir)
    cache = WorkbookCache(settings.schedule_source_url, data_dir / "cache", settings.xlsx_cache_ttl, settings.allow_stale_cache)
    schedules = ScheduleService(cache)
    user_config = UserConfig(data_dir / "users.json", settings.allowed_user_ids)
    users = UserService(user_config)
    bot = Bot(settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(AccessMiddleware(settings.allowed_user_ids))

    from aiogram import Router
    schedule_router = Router()
    notification_router = Router()
    register_schedule_handlers(schedule_router, schedules, users, settings.schedule_timezone)
    scheduler = AsyncIOScheduler(timezone=settings.schedule_timezone)
    register_notification_handlers(notification_router, schedules, users, scheduler, settings.schedule_timezone)
    dispatcher.include_router(schedule_router)
    dispatcher.include_router(notification_router)

    for user_id, profile in user_config.all().items():
        if profile.get("notification_enabled"):
            schedule_user_job(scheduler, bot, schedules, users, int(user_id), settings.schedule_timezone)
    scheduler.start()
    logging.getLogger(__name__).info("Бот запущен; режим Telegram Long Polling")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
