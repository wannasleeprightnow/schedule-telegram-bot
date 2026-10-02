from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.application.schedule_service import ScheduleService, render_schedule
from src.application.user_service import UserService
from src.presentation.telegram.keyboards import main_keyboard, settings_keyboard

logger = logging.getLogger(__name__)
router = Router()


class NotificationTime(StatesGroup):
    value = State()


def register_notification_handlers(router: Router, schedules: ScheduleService, users: UserService, scheduler: AsyncIOScheduler, timezone: str) -> None:
    @router.message(F.text == "⚙️ Настройки")
    async def settings(message: Message):
        profile = users.get(message.from_user.id)
        if not profile:
            await message.answer("Сначала настройте профиль: /start")
            return
        await message.answer(
            f"Профиль: {profile.get('class_course')} · группа {profile.get('group') or 'не выбрана'} · "
            f"пол { {'female': 'девушка', 'male': 'юноша'}.get(profile.get('gender'), 'не выбран') }\n"
            f"Уведомления: {'включены' if profile.get('notification_enabled') else 'выключены'} "
            f"({profile.get('notification_time', '21:00')})",
            reply_markup=settings_keyboard(bool(profile.get("notification_enabled"))),
        )

    @router.message(F.text == "🔔 Уведомления")
    async def notification_info(message: Message):
        profile = users.get(message.from_user.id)
        if not profile:
            await message.answer("Сначала настройте профиль: /start")
            return
        await message.answer("Уведомление отправляется на следующий учебный день. Нажмите кнопку и укажите время:", reply_markup=settings_keyboard(bool(profile.get("notification_enabled"))))

    @router.callback_query(F.data == "notifications:toggle")
    async def toggle(callback: CallbackQuery, state: FSMContext):
        profile = users.get(callback.from_user.id)
        if not profile:
            await callback.answer("Сначала настройте профиль", show_alert=True)
            return
        profile["notification_enabled"] = not bool(profile.get("notification_enabled"))
        users.save_profile(callback.from_user.id, profile)
        if profile["notification_enabled"]:
            await state.set_state(NotificationTime.value)
            await callback.message.answer("Введите время уведомления в формате ЧЧ:ММ (например, 21:00):")
        else:
            scheduler.remove_job(f"daily-{callback.from_user.id}") if scheduler.get_job(f"daily-{callback.from_user.id}") else None
            await callback.message.answer("Ежедневные уведомления выключены.", reply_markup=main_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "notifications:time")
    async def change_notification_time(callback: CallbackQuery, state: FSMContext):
        await state.set_state(NotificationTime.value)
        await callback.message.answer("Введите время уведомления в формате ЧЧ:ММ (например, 21:00):")
        await callback.answer()

    @router.message(NotificationTime.value, F.text)
    async def set_notification_time(message: Message, state: FSMContext):
        try:
            notification_time = datetime.strptime(message.text.strip(), "%H:%M").time()
        except ValueError:
            await message.answer("Укажите время как ЧЧ:ММ, например 21:00.")
            return
        profile = users.get(message.from_user.id)
        if not profile:
            await state.clear()
            return
        profile["notification_time"] = notification_time.strftime("%H:%M")
        users.save_profile(message.from_user.id, profile)
        if profile.get("notification_enabled"):
            schedule_user_job(scheduler, message.bot, schedules, users, message.from_user.id, timezone)
        await state.clear()
        status = "Уведомления включены" if profile.get("notification_enabled") else "Время сохранено; уведомления пока выключены"
        await message.answer(f"{status}. Время: {profile['notification_time']}.", reply_markup=main_keyboard())


def schedule_user_job(scheduler: AsyncIOScheduler, bot, schedules: ScheduleService, users: UserService, user_id: int, timezone: str) -> None:
    profile = users.get(user_id)
    if not profile or not profile.get("notification_enabled"):
        return
    try:
        hour, minute = (int(part) for part in profile.get("notification_time", "21:00").split(":"))
    except (ValueError, TypeError):
        logger.warning("Некорректное время уведомления пользователя %s", user_id)
        return
    scheduler.add_job(
        send_daily_notification,
        CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id=f"daily-{user_id}",
        replace_existing=True,
        kwargs={"bot": bot, "schedules": schedules, "users": users, "user_id": user_id, "timezone": timezone},
        misfire_grace_time=3600,
    )


async def send_daily_notification(bot, schedules: ScheduleService, users: UserService, user_id: int, timezone: str) -> None:
    profile = users.get(user_id)
    if not profile or not profile.get("notification_enabled"):
        return
    target = datetime.now(ZoneInfo(timezone)).date() + timedelta(days=1)
    while target.weekday() == 6:
        target += timedelta(days=1)
    try:
        schedule = await schedules.get_schedule(target, profile["class_course"], profile.get("group"), profile.get("gender"))
        await bot.send_message(user_id, render_schedule(schedule))
    except Exception as exc:
        logger.exception("Ошибка ежедневного уведомления пользователя %s", user_id)
        reason = "Google Sheets недоступен." if "получить актуальное расписание" in str(exc) else "ошибка при разборе расписания."
        try:
            await bot.send_message(user_id, f"⚠️ Не удалось автоматически получить расписание на следующий учебный день.\nПричина: {reason}\nПроверьте расписание вручную.")
        except Exception:
            logger.exception("Не удалось отправить сообщение об ошибке пользователю %s", user_id)
