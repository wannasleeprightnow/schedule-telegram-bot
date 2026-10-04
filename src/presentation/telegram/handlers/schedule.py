from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.application.schedule_service import ScheduleService, render_schedule
from src.application.user_service import UserService
from src.presentation.telegram.keyboards import choice_keyboard, gender_keyboard, main_keyboard, profile_types

router = Router()


class DateInput(StatesGroup):
    value = State()


def register_schedule_handlers(router: Router, schedules: ScheduleService, users: UserService, timezone: str) -> None:
    @router.message(CommandStart())
    async def start(message: Message):
        user_id = message.from_user.id
        profile = users.get(user_id)
        if not profile:
            await message.answer("Выберите тип расписания:", reply_markup=profile_types())
            return
        if profile.get("gender") not in {"female", "male"}:
            await message.answer("Выберите пол для точного поиска зала в расписании:", reply_markup=gender_keyboard())
            return
        await message.answer("Расписание Академии. Выберите действие:", reply_markup=main_keyboard())

    @router.callback_query(F.data == "profile:edit")
    @router.callback_query(F.data.startswith("type:"))
    async def choose_type(callback: CallbackQuery, state: FSMContext):
        if callback.data == "profile:edit":
            await callback.message.answer("Выберите тип расписания:", reply_markup=profile_types())
            await callback.answer()
            return
        category = callback.data.split(":", 1)[1]
        try:
            classes = (await schedules.available_classes()).get(category, [])
        except Exception:
            await callback.message.answer("⚠️ Не удалось загрузить список классов. Попробуйте позже.")
            await callback.answer()
            return
        if not classes:
            await callback.answer("Варианты не найдены в книге", show_alert=True)
            return
        await state.update_data(schedule_type=category, classes=classes)
        await callback.message.answer("Выберите класс или курс:", reply_markup=choice_keyboard("class", classes))
        await callback.answer()

    @router.callback_query(F.data.startswith("class:"))
    async def choose_class(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        classes = data.get("classes", [])
        index = int(callback.data.split(":", 1)[1])
        if index >= len(classes):
            await callback.answer("Вариант устарел, начните сначала", show_alert=True)
            return
        class_course = classes[index]
        await state.update_data(class_course=class_course)
        groups = await _groups_for(schedules, class_course)
        if groups:
            await callback.message.answer("Выберите группу или пропустите этот шаг:", reply_markup=choice_keyboard("group", groups, include_skip=True))
        else:
            await callback.message.answer("Выберите пол для точного поиска зала в расписании:", reply_markup=gender_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("group:"))
    async def choose_group(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        group = None
        if callback.data != "group:skip":
            groups = await _groups_for(schedules, data.get("class_course", ""))
            index = int(callback.data.split(":", 1)[1])
            group = groups[index] if index < len(groups) else None
        await state.update_data(group=group)
        await callback.message.answer("Выберите пол для точного поиска зала в расписании:", reply_markup=gender_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("gender:"))
    async def choose_gender(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        gender = callback.data.split(":", 1)[1]
        if gender not in {"female", "male"}:
            await callback.answer("Неизвестный вариант", show_alert=True)
            return
        if not data.get("class_course"):
            profile = users.get(callback.from_user.id)
            if not profile:
                await callback.answer("Сначала настройте профиль", show_alert=True)
                return
            profile["gender"] = gender
            users.save_profile(callback.from_user.id, profile)
            await callback.message.answer("Пол сохранён для поиска зала.", reply_markup=main_keyboard())
            await state.clear()
            await callback.answer()
            return
        await _save_profile(
            callback,
            users,
            state,
            data.get("class_course", ""),
            data.get("group"),
            gender,
        )
        await callback.answer()

    @router.message(F.text == "📅 Сегодня")
    async def today(message: Message):
        await _send_schedule(message, schedules, users, datetime.now(ZoneInfo(timezone)).date())

    @router.message(F.text == "📆 Выбрать дату")
    async def choose_date(message: Message, state: FSMContext):
        await state.set_state(DateInput.value)
        await message.answer("Введите дату в формате ДД.ММ.ГГГГ:")

    @router.message(DateInput.value, F.text)
    async def date_input(message: Message, state: FSMContext):
        try:
            requested_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        except ValueError:
            await message.answer("Не распознал дату. Пример: 02.10.2026")
            return
        await state.clear()
        await _send_schedule(message, schedules, users, requested_date)


async def _save_profile(callback: CallbackQuery, users: UserService, state: FSMContext, class_course: str, group: str | None, gender: str):
    data = await state.get_data()
    existing = users.get(callback.from_user.id) or {}
    try:
        users.save_profile(callback.from_user.id, {
            "schedule_type": data.get("schedule_type", "school"),
            "class_course": class_course,
            "group": group,
            "gender": gender,
            "notification_enabled": existing.get("notification_enabled", False),
            "notification_time": existing.get("notification_time", "21:00"),
        })
    except (ValueError, PermissionError) as exc:
        await callback.message.answer(str(exc))
        return
    await state.clear()
    await callback.message.answer("Профиль сохранён.", reply_markup=main_keyboard())


async def _send_schedule(message: Message, schedules: ScheduleService, users: UserService, requested_date: date):
    profile = users.get(message.from_user.id)
    if not profile:
        await message.answer("Сначала настройте профиль: /start")
        return

    loading_message = await message.answer("⏳ Получаю расписание…")
    try:
        schedule = await schedules.get_schedule(requested_date, profile["class_course"], profile.get("group"), profile.get("gender"))
        response_text = render_schedule(schedule)
        response_markup = main_keyboard()
    except Exception as exc:
        response_text = f"⚠️ Не удалось получить расписание.\nПричина: {exc}"
        response_markup = None

    try:
        await loading_message.delete()
    except Exception:
        # A failed cleanup should not prevent the user from receiving the result.
        pass

    await message.answer(response_text, reply_markup=response_markup)


async def _groups_for(schedules: ScheduleService, class_course: str) -> list[str]:
    return await schedules.available_groups(class_course)
