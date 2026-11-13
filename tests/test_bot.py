import asyncio
import base64
import json
import os
import tempfile
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "t.sqlite").replace("\\", "/")
os.environ["LIQPAY_PUBLIC_KEY"] = "sandbox_pub"
os.environ["LIQPAY_PRIVATE_KEY"] = "sandbox_priv"

import pytest

from bot.seed import seed
from bot.services import liqpay
from bot.services.slots import free_slots
from webadmin.emulator import Emulator

DAY = datetime(2026, 11, 16)  # понеділок


def at(h, m=0):
    return DAY.replace(hour=h, minute=m)


def test_free_slots_basic():
    slots = free_slots((at(10), at(13)), [], 60, now=DAY - timedelta(days=1))
    assert [s.hour for s in slots] == [10, 10, 11, 11, 12]


def test_free_slots_respects_busy_and_duration():
    busy = [(at(11), at(12))]
    slots = free_slots((at(10), at(14)), busy, 90, now=DAY - timedelta(days=1))
    # 90 хвилин не влазять перед 11:00 і не перетинаються з 11–12
    assert [s.strftime("%H:%M") for s in slots] == ["12:00", "12:30"]


def test_no_slots_too_soon_today():
    slots = free_slots((at(10), at(14)), [], 30, now=at(11, 10))
    assert slots[0] == at(12, 30)


def test_liqpay_signature_roundtrip():
    link = liqpay.payment_link(7, 300, "Передоплата")
    data = link.split("data=")[1].split("&")[0]
    signature = link.split("signature=")[1]
    payload = liqpay.parse_callback(data, signature)
    assert payload["order_id"] == "booking-7" and payload["amount"] == 300

    with pytest.raises(ValueError):
        liqpay.parse_callback(base64.b64encode(json.dumps({"x": 1}).encode()).decode(), signature)


def test_full_booking_flow_through_handlers():
    """Проходимо весь сценарій через справжній Dispatcher, як живий клієнт."""

    async def scenario():
        await seed()
        emu = Emulator()
        await emu.send_text("/start")
        await emu.send_text("📅 Записатися")

        def last_buttons():
            msg = next(m for m in reversed(emu.chat.messages) if m["buttons"])
            return msg["id"], [b for row in msg["buttons"] for b in row]

        mid, buttons = last_buttons()
        await emu.press(mid, buttons[0]["data"])                       # Жіноча стрижка
        mid, buttons = last_buttons()
        assert any("Олена" in b["text"] for b in buttons)
        await emu.press(mid, buttons[0]["data"])                       # перший майстер
        mid, buttons = last_buttons()
        await emu.press(mid, buttons[0]["data"])                       # перший доступний день
        mid, buttons = last_buttons()
        await emu.press(mid, buttons[0]["data"])                       # перший час
        await emu.send_contact()
        mid, buttons = last_buttons()
        await emu.press(mid, buttons[0]["data"])                       # підтвердити

        assert "Ви записані" in emu.chat.messages[-1]["text"]

        await emu.send_text("🗓 Мої записи")
        assert "Жіноча стрижка" in emu.chat.messages[-1]["text"]

    asyncio.run(scenario())
