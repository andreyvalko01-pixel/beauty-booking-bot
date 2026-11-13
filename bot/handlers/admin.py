"""Команди адміністратора салону прямо в Telegram."""

import asyncio
from datetime import date, datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select

from ..config import settings
from ..models import Booking, Client, Session

router = Router()
router.message.filter(F.from_user.id.in_(settings.admins))


@router.message(Command("today"))
async def today(message: Message):
    start = datetime.combine(date.today(), time.min)
    async with Session() as session:
        bookings = (await session.scalars(
            select(Booking).where(Booking.starts_at >= start, Booking.starts_at < start + timedelta(days=1),
                                  Booking.status.in_(("confirmed", "pending_payment")))
            .order_by(Booking.master_id, Booking.starts_at)
        )).all()

    if not bookings:
        await message.answer("Сьогодні записів немає.")
        return

    lines, current_master = [f"📋 Записи на {date.today():%d.%m}:"], None
    for b in bookings:
        if b.master.name != current_master:
            current_master = b.master.name
            lines.append(f"\n👩 {current_master}")
        mark = " ⏳" if b.status == "pending_payment" else ""
        lines.append(f"  {b.starts_at:%H:%M} {b.service.name} — {b.client.name}, {b.client.phone or '—'}{mark}")
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def stats(message: Message):
    since = datetime.now() - timedelta(days=30)
    async with Session() as session:
        rows = (await session.execute(
            select(Booking.status, func.count()).where(Booking.created_at >= since).group_by(Booking.status)
        )).all()
        clients = await session.scalar(select(func.count(Client.id)))
    by_status = dict(rows)
    await message.answer(
        "📊 За 30 днів:\n"
        f"Записів: {sum(by_status.values())}\n"
        f"Підтверджено: {by_status.get('confirmed', 0) + by_status.get('done', 0)}\n"
        f"Скасовано: {by_status.get('cancelled', 0)}\n"
        f"Клієнтів у базі: {clients}"
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, command: CommandObject, bot: Bot):
    if not command.args:
        await message.answer("Формат: /broadcast Текст розсилки")
        return

    async with Session() as session:
        ids = (await session.scalars(select(Client.telegram_id))).all()

    sent = blocked = 0
    for chat_id in ids:
        try:
            await bot.send_message(chat_id, command.args)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1          # клієнт заблокував бота
        await asyncio.sleep(0.05)  # ліміт Telegram ~30 повідомлень на секунду
    await message.answer(f"Розсилку завершено: доставлено {sent}, заблокували бота {blocked}.")
