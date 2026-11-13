"""Запуск бота: python -m bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import settings
from .handlers import admin, booking, my_bookings
from .models import init_db
from .reminders import reminders_loop


_dispatcher: Dispatcher | None = None


def build_dispatcher() -> Dispatcher:
    """Роутери в aiogram можна підключити лише до одного Dispatcher, тому створюємо його один раз."""
    global _dispatcher
    if _dispatcher:
        return _dispatcher

    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        storage = RedisStorage.from_url(settings.redis_url)
    else:
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)
    # порядок важливий: адмін-команди і загальні — до сценарію запису
    dp.include_routers(admin.router, my_bookings.router, booking.router)
    _dispatcher = dp
    return dp


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await init_db()

    bot = Bot(settings.bot_token)
    dp = build_dispatcher()
    reminders = asyncio.create_task(reminders_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()


if __name__ == "__main__":
    asyncio.run(main())
