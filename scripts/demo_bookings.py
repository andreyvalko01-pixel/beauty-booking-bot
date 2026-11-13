"""Заповнює базу тестовими записами на сьогодні — щоб подивитися панель адміністратора.

    python -m bot.seed && python scripts/demo_bookings.py
"""

import asyncio
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from bot.models import Booking, Client, Master, Session  # noqa: E402

NAMES = ["Наталія Бондар", "Юлія Шевчук", "Катерина Мороз", "Олександра Ткач", "Вікторія Лисенко",
         "Дарина Кравець", "Софія Павленко", "Ганна Руденко", "Тетяна Савчук", "Аліна Гончар"]


async def main():
    random.seed(7)
    async with Session() as session:
        masters = (await session.scalars(select(Master))).all()
        clients = []
        for i, name in enumerate(NAMES):
            client = Client(telegram_id=500000 + i, name=name, phone=f"+38067{random.randint(1000000, 9999999)}")
            session.add(client)
            clients.append(client)
        await session.flush()

        for master in masters:
            cursor = datetime.combine(date.today(), time(10))
            while cursor.hour < 18:
                service = random.choice(master.services)
                if random.random() < 0.7:
                    session.add(Booking(
                        client_id=random.choice(clients).id, master_id=master.id, service_id=service.id,
                        starts_at=cursor, ends_at=cursor + timedelta(minutes=service.duration),
                        status="pending_payment" if service.price >= 1000 and random.random() < 0.4 else "confirmed",
                    ))
                cursor += timedelta(minutes=service.duration + random.choice([0, 30, 60]))
        await session.commit()
    print("Тестові записи додано")


asyncio.run(main())
