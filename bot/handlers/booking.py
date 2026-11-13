"""Сценарій запису: послуга → майстер → день → час → телефон → підтвердження."""

from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from .. import keyboards as kb
from ..config import settings
from ..models import Booking, Client, Master, MasterService, Service, Session
from ..services import gcalendar, liqpay
from ..services.slots import available_days, get_free_slots

router = Router()


class Flow(StatesGroup):
    service = State()
    master = State()
    day = State()
    time = State()
    phone = State()
    confirm = State()


async def get_client(session, user) -> Client:
    client = await session.scalar(select(Client).where(Client.telegram_id == user.id))
    if not client:
        client = Client(telegram_id=user.id, name=user.full_name or "Клієнт")
        session.add(client)
        await session.commit()
    return client


# ---------- кроки ----------

async def show_services(target: Message, state: FSMContext, edit: bool = False):
    async with Session() as session:
        services = (await session.scalars(select(Service).order_by(Service.id))).all()
    await state.set_state(Flow.service)
    text = "Оберіть послугу:"
    if edit:
        await target.edit_text(text, reply_markup=kb.services_kb(services))
    else:
        await target.answer(text, reply_markup=kb.services_kb(services))


async def show_masters(message: Message, state: FSMContext):
    data = await state.get_data()
    async with Session() as session:
        masters = (await session.scalars(
            select(Master).join(MasterService).where(MasterService.service_id == data["service_id"])
        )).all()
    await state.set_state(Flow.master)
    await message.edit_text(f"{data['service_name']}\n\nДо кого записати?", reply_markup=kb.masters_kb(masters))


async def show_days(message: Message, state: FSMContext):
    data = await state.get_data()
    async with Session() as session:
        master = await session.get(Master, data["master_id"])
        days = await available_days(session, master, data["duration"], exclude_id=data.get("move_booking_id"))

    await state.set_state(Flow.day)
    if not days:
        await message.edit_text("На найближчі два тижні вільних вікон немає 😔 Оберіть іншого майстра.",
                                reply_markup=kb.days_kb([]))
        return
    await message.edit_text(f"{data['service_name']} · {master.name}\n\nОберіть день:", reply_markup=kb.days_kb(days))


async def show_times(message: Message, state: FSMContext):
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    async with Session() as session:
        master = await session.get(Master, data["master_id"])
        slots = await get_free_slots(session, master, day, data["duration"], exclude_id=data.get("move_booking_id"))
    await state.set_state(Flow.time)
    await message.edit_text(f"{kb.human_date(day)}, {master.name}\n\nОберіть час:", reply_markup=kb.times_kb(slots))


async def show_confirm(message: Message, state: FSMContext, edit: bool = True):
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    prepay = liqpay.prepayment_for(data["price"])
    text = (
        "Перевірте, будь ласка:\n\n"
        f"💇 {data['service_name']}\n"
        f"👩 {data['master_name']}\n"
        f"📅 {kb.human_date(day)}, {data['time']}\n"
        f"💰 {data['price']} ₴"
    )
    if prepay:
        text += f"\n\nДля підтвердження потрібна передоплата {prepay} ₴."
    await state.set_state(Flow.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb.confirm_kb())
    else:
        await message.answer(text, reply_markup=kb.confirm_kb())


# ---------- обробники ----------

@router.message(F.text == kb.BTN_BOOK)
async def start_booking(message: Message, state: FSMContext):
    await state.clear()
    await show_services(message, state)


@router.callback_query(kb.Pick.filter(F.step == "service"))
async def on_service(call: CallbackQuery, callback_data: kb.Pick, state: FSMContext):
    async with Session() as session:
        service = await session.get(Service, int(callback_data.value))
    await state.update_data(service_id=service.id, service_name=service.name, duration=service.duration, price=service.price)
    await show_masters(call.message, state)
    await call.answer()


@router.callback_query(kb.Pick.filter(F.step == "master"))
async def on_master(call: CallbackQuery, callback_data: kb.Pick, state: FSMContext):
    data = await state.get_data()
    async with Session() as session:
        if callback_data.value == "any":
            # "будь-хто" — беремо майстра, у якого найближче вільне вікно
            masters = (await session.scalars(
                select(Master).join(MasterService).where(MasterService.service_id == data["service_id"])
            )).all()
            best, best_slot = None, None
            for m in masters:
                for i in range(settings.booking_days_ahead):
                    slots = await get_free_slots(session, m, date.today() + timedelta(days=i), data["duration"])
                    if slots:
                        if not best_slot or slots[0] < best_slot:
                            best, best_slot = m, slots[0]
                        break
            if not best:
                await call.answer("Вільних вікон немає", show_alert=True)
                return
            master = best
        else:
            master = await session.get(Master, int(callback_data.value))

    await state.update_data(master_id=master.id, master_name=master.name)
    await show_days(call.message, state)
    await call.answer()


@router.callback_query(kb.Pick.filter(F.step == "day"))
async def on_day(call: CallbackQuery, callback_data: kb.Pick, state: FSMContext):
    await state.update_data(day=callback_data.value)
    await show_times(call.message, state)
    await call.answer()


@router.callback_query(kb.Pick.filter(F.step == "time"))
async def on_time(call: CallbackQuery, callback_data: kb.Pick, state: FSMContext):
    raw = callback_data.value
    await state.update_data(time=f"{raw[:2]}:{raw[2:]}")
    await call.answer()

    data = await state.get_data()
    if data.get("move_booking_id"):
        await finish_move(call, state)
        return

    async with Session() as session:
        client = await get_client(session, call.from_user)
    if not client.phone:
        await state.set_state(Flow.phone)
        await call.message.edit_text("Залишився один крок — номер телефону, щоб майстер міг з вами зв'язатися.")
        await call.message.answer("Натисніть кнопку нижче 👇", reply_markup=kb.share_phone())
        return
    await show_confirm(call.message, state)


@router.message(Flow.phone, F.contact)
async def on_contact(message: Message, state: FSMContext):
    async with Session() as session:
        client = await get_client(session, message.from_user)
        client.phone = "+" + message.contact.phone_number.lstrip("+")
        client.name = message.contact.first_name or client.name
        session.add(client)
        await session.commit()
    await message.answer("Дякую! 👍", reply_markup=kb.main_menu())
    await show_confirm(message, state, edit=False)


@router.message(Flow.phone)
async def on_phone_text(message: Message):
    await message.answer("Будь ласка, скористайтесь кнопкою «📱 Надіслати номер».", reply_markup=kb.share_phone())


@router.callback_query(kb.Pick.filter(F.step == "confirm"))
async def on_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    starts = datetime.combine(date.fromisoformat(data["day"]), datetime.strptime(data["time"], "%H:%M").time())

    async with Session() as session:
        master = await session.get(Master, data["master_id"])
        # поки людина думала, хтось міг зайняти цей час — перевіряємо ще раз
        free = await get_free_slots(session, master, starts.date(), data["duration"])
        if starts not in free:
            await call.answer("На жаль, цей час щойно зайняли. Оберіть інший.", show_alert=True)
            await show_times(call.message, state)
            return

        client = await get_client(session, call.from_user)
        prepay = liqpay.prepayment_for(data["price"])
        booking = Booking(
            client_id=client.id,
            master_id=master.id,
            service_id=data["service_id"],
            starts_at=starts,
            ends_at=starts + timedelta(minutes=data["duration"]),
            status="pending_payment" if prepay else "confirmed",
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking, ["client", "master", "service"])

        booking.google_event_id = await gcalendar.upsert_event(booking)
        await session.commit()

    await state.clear()
    text = (
        f"🎉 Ви записані!\n\n{data['service_name']}, {data['master_name']}\n"
        f"📅 {kb.human_date(starts.date())}, {data['time']}\n📍 {settings.salon_address}\n\n"
        "Нагадаємо за добу і за 2 години до візиту."
    )
    if prepay:
        link = liqpay.payment_link(booking.id, prepay, f"Передоплата: {data['service_name']}, {starts:%d.%m %H:%M}")
        await call.message.edit_text(text + f"\n\nЗапис підтвердиться після передоплати {prepay} ₴.",
                                     reply_markup=kb.pay_kb(link))
    else:
        await call.message.edit_text(text)
    await call.answer()


@router.callback_query(kb.Pick.filter(F.step == "back"))
async def on_back(call: CallbackQuery, callback_data: kb.Pick, state: FSMContext):
    screens = {"service": lambda: show_services(call.message, state, edit=True),
               "master": lambda: show_masters(call.message, state),
               "day": lambda: show_days(call.message, state)}
    await screens[callback_data.value]()
    await call.answer()


async def finish_move(call: CallbackQuery, state: FSMContext):
    """Кінець сценарію перенесення: той самий майстер і послуга, новий час."""
    data = await state.get_data()
    starts = datetime.combine(date.fromisoformat(data["day"]), datetime.strptime(data["time"], "%H:%M").time())

    async with Session() as session:
        booking = await session.get(Booking, data["move_booking_id"])
        booking.starts_at = starts
        booking.ends_at = starts + timedelta(minutes=booking.service.duration)
        booking.reminded_day = booking.reminded_2h = False
        booking.google_event_id = await gcalendar.upsert_event(booking)
        await session.commit()

    await state.clear()
    await call.message.edit_text(f"🔁 Запис перенесено на {kb.human_date(starts.date())}, {data['time']}.")
