from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from .. import keyboards as kb
from ..config import settings
from ..models import Booking, Client, Session
from ..services import gcalendar
from .booking import Flow, get_client, show_days

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    async with Session() as session:
        await get_client(session, message.from_user)
    await message.answer(
        f"Вітаємо в {settings.salon_name}! 🌸\n\n"
        "Тут можна записатися до майстра за хвилину — без дзвінків і очікування. "
        "Оберіть, що вас цікавить:",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == kb.BTN_CONTACTS)
async def contacts(message: Message):
    await message.answer(f"📍 {settings.salon_address}\n🕙 Щодня 9:00–21:00\n📞 +380 67 555 44 33")


@router.message(F.text == kb.BTN_MY)
async def my_bookings(message: Message):
    async with Session() as session:
        bookings = (await session.scalars(
            select(Booking).join(Client).where(
                Client.telegram_id == message.from_user.id,
                Booking.starts_at >= datetime.now(),
                Booking.status.in_(("confirmed", "pending_payment")),
            ).order_by(Booking.starts_at)
        )).all()

    if not bookings:
        await message.answer("Активних записів немає. Натисніть «📅 Записатися», щоб обрати час.")
        return

    for b in bookings:
        status = "" if b.status == "confirmed" else "\n⏳ очікує передоплату"
        await message.answer(
            f"{b.service.name}\n👩 {b.master.name}\n📅 {kb.human_date(b.starts_at.date())}, {b.starts_at:%H:%M}{status}",
            reply_markup=kb.booking_actions_kb(b.id),
        )


async def _own_booking(session, call: CallbackQuery, booking_id: int) -> Booking | None:
    booking = await session.get(Booking, booking_id)
    if not booking or booking.client.telegram_id != call.from_user.id:
        await call.answer("Запис не знайдено", show_alert=True)
        return None
    return booking


@router.callback_query(kb.BookingAction.filter(F.action == "cancel"))
async def ask_cancel(call: CallbackQuery, callback_data: kb.BookingAction):
    await call.message.edit_reply_markup(reply_markup=kb.cancel_confirm_kb(callback_data.booking_id))
    await call.answer()


@router.callback_query(kb.BookingAction.filter(F.action == "keep"))
async def keep(call: CallbackQuery, callback_data: kb.BookingAction):
    await call.message.edit_reply_markup(reply_markup=kb.booking_actions_kb(callback_data.booking_id))
    await call.answer("Залишили як є 👍")


@router.callback_query(kb.BookingAction.filter(F.action == "confirm_cancel"))
async def cancel(call: CallbackQuery, callback_data: kb.BookingAction):
    async with Session() as session:
        booking = await _own_booking(session, call, callback_data.booking_id)
        if not booking:
            return
        booking.status = "cancelled"
        await gcalendar.delete_event(booking)
        await session.commit()
    await call.message.edit_text(call.message.text + "\n\n❌ Скасовано")
    await call.answer()


@router.callback_query(kb.BookingAction.filter(F.action == "move"))
async def move(call: CallbackQuery, callback_data: kb.BookingAction, state: FSMContext):
    async with Session() as session:
        booking = await _own_booking(session, call, callback_data.booking_id)
        if not booking:
            return

    await state.set_state(Flow.day)
    await state.update_data(
        move_booking_id=booking.id,
        service_id=booking.service_id,
        service_name=booking.service.name,
        duration=booking.service.duration,
        price=booking.service.price,
        master_id=booking.master_id,
        master_name=booking.master.name,
    )
    await show_days(call.message, state)
    await call.answer()
