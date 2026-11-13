"""Початкові дані: послуги, майстри, графік. Запуск: python -m bot.seed"""

import asyncio
from datetime import time

from sqlalchemy import select

from .models import Master, Service, Session, WorkDay, init_db

SERVICES = [
    ("Жіноча стрижка", 60, 700),
    ("Стрижка + укладка", 90, 1100),
    ("Фарбування в один тон", 120, 1800),
    ("Манікюр з покриттям", 90, 650),
    ("Педикюр", 90, 800),
    ("Корекція брів", 30, 300),
]

# ім'я, спеціалізація, послуги (індекси в SERVICES), робочі дні
MASTERS = [
    ("Олена", "перукар-стиліст", [0, 1, 2], [0, 1, 2, 3, 4]),
    ("Ірина", "колорист", [0, 1, 2], [1, 2, 3, 4, 5]),
    ("Марія", "майстер манікюру", [3, 4], [0, 2, 3, 4, 5]),
    ("Анна", "бровист", [5, 3], [0, 1, 3, 5, 6]),
]


async def seed():
    await init_db()
    async with Session() as session:
        if await session.scalar(select(Service.id).limit(1)):
            print("Дані вже є, пропускаю")
            return

        services = [Service(name=n, duration=d, price=p) for n, d, p in SERVICES]
        session.add_all(services)
        for name, specialty, svc_idx, days in MASTERS:
            master = Master(name=name, specialty=specialty, services=[services[i] for i in svc_idx])
            master.schedule = [WorkDay(weekday=d, start=time(10), end=time(20)) for d in days]
            session.add(master)
        await session.commit()
    print("Готово")


if __name__ == "__main__":
    asyncio.run(seed())
