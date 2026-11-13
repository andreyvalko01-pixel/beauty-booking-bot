"""Розрахунок вільних вікон у майстра."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from ..config import settings
from ..models import Booking, Master

ACTIVE = ("confirmed", "pending_payment")


def day_window(master: Master, day: date) -> tuple[datetime, datetime] | None:
    for wd in master.schedule:
        if wd.weekday == day.weekday():
            return datetime.combine(day, wd.start), datetime.combine(day, wd.end)
    return None


def free_slots(window: tuple[datetime, datetime] | None, busy: list[tuple[datetime, datetime]],
               duration: int, now: datetime, step: int = 30) -> list[datetime]:
    """Чиста функція без БД — легко тестувати.

    window   — робочий час майстра в цей день
    busy     — вже зайняті проміжки
    duration — тривалість послуги в хвилинах
    """
    if not window:
        return []
    start, end = window
    length = timedelta(minutes=duration)
    result = []

    current = start
    while current + length <= end:
        # на сьогодні не пропонуємо час, до якого менше години — майстер не встигне підготуватись
        if current >= now + timedelta(hours=1):
            overlaps = any(current < b_end and current + length > b_start for b_start, b_end in busy)
            if not overlaps:
                result.append(current)
        current += timedelta(minutes=step)
    return result


async def get_free_slots(session, master: Master, day: date, duration: int, now: datetime | None = None,
                         exclude_id: int | None = None) -> list[datetime]:
    """exclude_id — запис, який зараз переносять: його поточний час теж вважаємо вільним."""
    now = now or datetime.now()
    rows = await session.execute(
        select(Booking.starts_at, Booking.ends_at).where(
            Booking.master_id == master.id,
            Booking.status.in_(ACTIVE),
            Booking.id != (exclude_id or 0),
            Booking.starts_at >= datetime.combine(day, time.min),
            Booking.starts_at < datetime.combine(day + timedelta(days=1), time.min),
        )
    )
    busy = [(r.starts_at, r.ends_at) for r in rows]
    return free_slots(day_window(master, day), busy, duration, now, settings.slot_minutes)


async def available_days(session, master: Master, duration: int, exclude_id: int | None = None) -> list[date]:
    """Дні найближчих двох тижнів, у які є хоч одне вільне вікно."""
    today = date.today()
    days = []
    for i in range(settings.booking_days_ahead):
        day = today + timedelta(days=i)
        if await get_free_slots(session, master, day, duration, exclude_id=exclude_id):
            days.append(day)
    return days
