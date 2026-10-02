from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📆 Выбрать дату")], [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🔔 Уведомления")]], resize_keyboard=True)


def profile_types() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начальная школа", callback_data="type:primary")],
        [InlineKeyboardButton(text="5–9 класс", callback_data="type:school")],
        [InlineKeyboardButton(text="I–III курс", callback_data="type:course")],
        [InlineKeyboardButton(text="ОТТ", callback_data="type:ott")],
    ])


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Девушка", callback_data="gender:female")],
        [InlineKeyboardButton(text="Юноша", callback_data="gender:male")],
    ])


def choice_keyboard(prefix: str, values: list[str], include_skip: bool = False) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=value, callback_data=f"{prefix}:{index}")] for index, value in enumerate(values)]
    if include_skip:
        buttons.append([InlineKeyboardButton(text="Без выбора группы", callback_data="group:skip")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "Выключить уведомления" if enabled else "Включить уведомления"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label, callback_data="notifications:toggle")],
        [InlineKeyboardButton(text="Изменить время уведомления", callback_data="notifications:time")],
        [InlineKeyboardButton(text="Изменить профиль", callback_data="profile:edit")],
    ])
