"""Inline-клавиатуры. Часовой пояс отображения — Москва."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def start_choice_kb(has_visits: bool) -> InlineKeyboardMarkup:
    """Первичный / Вторичный. Обе кнопки всегда; при отсутствии записей по «Вторичный» бот подскажет."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Первичный приём", callback_data="primary"),
        InlineKeyboardButton(text="Вторичный приём", callback_data="secondary"),
    )
    return builder.as_markup()


def yes_no_kb(yes_data: str = "yes", no_data: str = "no") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да", callback_data=yes_data),
        InlineKeyboardButton(text="Нет", callback_data=no_data),
    )
    return builder.as_markup()


def doctors_kb(doctors: list[dict], prefix: str = "doc") -> InlineKeyboardMarkup:
    """Список врачей: callback_data = prefix:doctor_id."""
    builder = InlineKeyboardBuilder()
    for d in doctors:
        builder.row(
            InlineKeyboardButton(
                text=f"{d['full_name']} — {d['specialty']}",
                callback_data=f"{prefix}:{d['id']}",
            )
        )
    return builder.as_markup()


def slots_kb(slots: list[dict], prefix: str = "slot") -> InlineKeyboardMarkup:
    """Слоты: текст — дата/время по Москве, callback_data = prefix:slot_id."""
    from db.crud import slot_start_moscow

    builder = InlineKeyboardBuilder()
    for s in slots:
        start = slot_start_moscow(s)
        label = start.strftime("%d.%m %H:%M")
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"{prefix}:{s['id']}")
        )
    return builder.as_markup()


def confirm_booking_kb() -> InlineKeyboardMarkup:
    """Подтвердить запись при создании."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Подтвердить запись", callback_data="confirm_booking"))
    return builder.as_markup()


def cancel_reminder_kb(appointment_id: int) -> InlineKeyboardMarkup:
    """В напоминании за 24 ч: только «Отменить запись»."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отменить запись", callback_data=f"cancel_app:{appointment_id}"))
    return builder.as_markup()
