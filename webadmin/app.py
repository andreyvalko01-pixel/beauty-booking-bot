"""Веб-панель адміністратора + callback LiqPay + емулятор чату для розробки.

Запуск: uvicorn webadmin.app:app --port 8080
"""

import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select

from bot.config import settings
from bot.models import Booking, Client, Master, Session, init_db
from bot.services import liqpay

BASE = Path(__file__).parent
app = FastAPI(title="Studio Bloom — адмін")
templates = Jinja2Templates(directory=BASE / "templates")
security = HTTPBasic()
emulator = None


@app.on_event("startup")
async def startup():
    await init_db()


def admin_only(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, settings.web_admin_user)
            and secrets.compare_digest(credentials.password, settings.web_admin_password)):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


@app.get("/", dependencies=[Depends(admin_only)])
async def dashboard(request: Request, day: date | None = None):
    day = day or date.today()
    start = datetime.combine(day, time.min)

    async with Session() as session:
        masters = (await session.scalars(select(Master).order_by(Master.id))).all()
        bookings = (await session.scalars(
            select(Booking).where(Booking.starts_at >= start, Booking.starts_at < start + timedelta(days=1),
                                  Booking.status != "cancelled").order_by(Booking.starts_at)
        )).all()

        month_ago = datetime.now() - timedelta(days=30)
        by_status = dict((await session.execute(
            select(Booking.status, func.count()).where(Booking.created_at >= month_ago).group_by(Booking.status)
        )).all())
        done = (await session.scalars(
            select(Booking).where(Booking.created_at >= month_ago, Booking.status.in_(("confirmed", "done")))
        )).all()
        revenue = sum(b.service.price for b in done)
        clients = await session.scalar(select(func.count(Client.id)))

    columns = {m.id: [] for m in masters}
    for b in bookings:
        columns.setdefault(b.master_id, []).append(b)

    hours = [f"{h:02d}:00" for h in range(10, 20)]
    return templates.TemplateResponse(request, "dashboard.html", {
        "day": day,
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "masters": masters,
        "columns": columns,
        "hours": hours,
        "total_today": len(bookings),
        "stats": by_status,
        "revenue": revenue,
        "clients": clients,
    })


@app.post("/broadcast", dependencies=[Depends(admin_only)])
async def broadcast(text: str = Form(...)):
    from aiogram import Bot

    bot = Bot(settings.bot_token)
    async with Session() as session:
        ids = (await session.scalars(select(Client.telegram_id))).all()
    sent = 0
    for chat_id in ids:
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except Exception:
            pass
    await bot.session.close()
    return RedirectResponse(f"/?sent={sent}", status_code=303)


@app.post("/liqpay/callback")
async def liqpay_callback(data: str = Form(...), signature: str = Form(...)):
    try:
        payload = liqpay.parse_callback(data, signature)
    except ValueError:
        raise HTTPException(400, "bad signature") from None

    if payload.get("status") not in ("success", "sandbox"):
        return {"ok": True}

    booking_id = int(payload["order_id"].removeprefix("booking-"))
    async with Session() as session:
        booking = await session.get(Booking, booking_id)
        if booking and booking.status == "pending_payment":
            booking.status = "confirmed"
            booking.prepaid = int(float(payload["amount"]))
            await session.commit()
    return {"ok": True}


# ---------- емулятор чату (лише для розробки) ----------

class EmuIn(BaseModel):
    text: str | None = None
    contact: bool = False
    message_id: int | None = None
    data: str | None = None


def get_emulator():
    global emulator
    if emulator is None:
        from .emulator import Emulator
        emulator = Emulator()
    return emulator


@app.get("/dev/chat")
def chat_page():
    return FileResponse(BASE / "templates" / "chat.html")


@app.get("/dev/chat/state")
async def chat_state():
    return get_emulator().state()


@app.post("/dev/chat/send")
async def chat_send(data: EmuIn):
    emu = get_emulator()
    if data.contact:
        await emu.send_contact()
    elif data.data:
        await emu.press(data.message_id, data.data)
    elif data.text:
        await emu.send_text(data.text)
    return emu.state()
