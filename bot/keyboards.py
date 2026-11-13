from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]

BTN_BOOK = "📅 Записатися"
BTN_MY = "🗓 Мої записи"
BTN_CONTACTS = "📍 Контакти"


class Pick(CallbackData, prefix="pick"):
    step: str          # service / master / day / time
    value: str


class BookingAction(CallbackData, prefix="bk"):
    action: str        # cancel / move / confirm_cancel
    booking_id: int


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_CONTACTS)]],
        resize_keyboard=True,
    )


def share_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Надіслати номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def back_button(builder: InlineKeyboardBuilder, to: str):
    builder.button(text="← Назад", callback_data=Pick(step="back", value=to))


def services_kb(services):
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(text=f"{s.name} · {s.price} ₴", callback_data=Pick(step="service", value=str(s.id)))
    kb.adjust(1)
    return kb.as_markup()


def masters_kb(masters):
    kb = InlineKeyboardBuilder()
    for m in masters:
        kb.button(text=f"{m.name} — {m.specialty}", callback_data=Pick(step="master", value=str(m.id)))
    kb.button(text="Будь-який вільний майстер", callback_data=Pick(step="master", value="any"))
    back_button(kb, "service")
    kb.adjust(1)
    return kb.as_markup()


def human_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def days_kb(days: list[date]):
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=human_date(d), callback_data=Pick(step="day", value=d.isoformat()))
    back_button(kb, "master")
    kb.adjust(3)
    return kb.as_markup()


def times_kb(slots: list[datetime]):
    kb = InlineKeyboardBuilder()
    for s in slots:
        # ":" — роздільник у callback_data aiogram, тому час передаємо як "1030"
        kb.button(text=s.strftime("%H:%M"), callback_data=Pick(step="time", value=s.strftime("%H%M")))
    back_button(kb, "day")
    kb.adjust(4)
    return kb.as_markup()


def confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Підтвердити", callback_data=Pick(step="confirm", value="yes"))
    kb.button(text="✏️ Змінити час", callback_data=Pick(step="back", value="day"))
    kb.adjust(1)
    return kb.as_markup()


def booking_actions_kb(booking_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Перенести", callback_data=BookingAction(action="move", booking_id=booking_id))
    kb.button(text="✖️ Скасувати", callback_data=BookingAction(action="cancel", booking_id=booking_id))
    kb.adjust(2)
    return kb.as_markup()


def cancel_confirm_kb(booking_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Так, скасувати", callback_data=BookingAction(action="confirm_cancel", booking_id=booking_id))
    kb.button(text="Ні, залишити", callback_data=BookingAction(action="keep", booking_id=booking_id))
    kb.adjust(2)
    return kb.as_markup()


def pay_kb(url: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатити передоплату", url=url)
    return kb.as_markup()
