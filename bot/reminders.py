"""Нагадування клієнтам за добу і за 2 години. Запускається фоновою задачею разом з ботом."""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select

from . import keyboards as kb
from .models import Booking, Session

log = logging.getLogger(__name__)
CHECK_EVERY = 60  # секунд


async def send_due_reminders(bot: Bot, now: datetime | None = None) -> int:
    now = now or datetime.now()
    sent = 0

    async with Session() as session:
        bookings = (await session.scalars(
            select(Booking).where(
                Booking.status == "confirmed",
                Booking.starts_at > now,
                Booking.starts_at <= now + timedelta(hours=24),
            )
        )).all()

        for b in bookings:
            left = b.starts_at - now
            if left <= timedelta(hours=2) and not b.reminded_2h:
                text = f"⏰ Чекаємо вас сьогодні о {b.starts_at:%H:%M}!\n{b.service.name}, майстер {b.master.name}"
                b.reminded_2h = b.reminded_day = True
            elif not b.reminded_day:
                text = (f"Нагадуємо: завтра о {b.starts_at:%H:%M} у вас {b.service.name.lower()} "
                        f"у майстра {b.master.name}. Якщо плани змінились — перенесіть або скасуйте запис 👇")
                b.reminded_day = True
            else:
                continue

            try:
                await bot.send_message(b.client.telegram_id, text, reply_markup=kb.booking_actions_kb(b.id))
                sent += 1
            except Exception as e:
                log.warning("Не вдалося нагадати клієнту %s: %s", b.client.telegram_id, e)

        await session.commit()
    return sent


async def reminders_loop(bot: Bot):
    while True:
        try:
            await send_due_reminders(bot)
        except Exception:
            log.exception("Помилка в нагадуваннях")
        await asyncio.sleep(CHECK_EVERY)
