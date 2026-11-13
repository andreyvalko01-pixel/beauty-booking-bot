"""Синхронізація записів з Google Calendar майстра.

Календар майстра треба розшарити на email сервісного акаунта (права "вносити зміни").
Якщо GOOGLE_CREDENTIALS не задано — синхронізація просто вимкнена.
"""

import asyncio
import logging
from functools import lru_cache

from ..config import settings
from ..models import Booking

log = logging.getLogger(__name__)


@lru_cache
def _service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_credentials, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _event_body(booking: Booking) -> dict:
    return {
        "summary": f"{booking.service.name} — {booking.client.name}",
        "description": f"Телефон: {booking.client.phone or '—'}\nЗапис #{booking.id} з Telegram-бота",
        "start": {"dateTime": booking.starts_at.isoformat(), "timeZone": settings.timezone},
        "end": {"dateTime": booking.ends_at.isoformat(), "timeZone": settings.timezone},
    }


def _enabled(booking: Booking) -> bool:
    return bool(settings.google_credentials and booking.master.google_calendar_id)


async def upsert_event(booking: Booking) -> str | None:
    if not _enabled(booking):
        return None

    def call():
        events = _service().events()
        calendar = booking.master.google_calendar_id
        if booking.google_event_id:
            return events.update(calendarId=calendar, eventId=booking.google_event_id, body=_event_body(booking)).execute()
        return events.insert(calendarId=calendar, body=_event_body(booking)).execute()

    try:
        event = await asyncio.to_thread(call)
        return event["id"]
    except Exception:
        # календар — допоміжна річ, запис у боті не повинен зламатись через нього
        log.exception("Google Calendar: не вдалося зберегти подію для запису #%s", booking.id)
        return booking.google_event_id


async def delete_event(booking: Booking):
    if not (_enabled(booking) and booking.google_event_id):
        return
    try:
        await asyncio.to_thread(
            _service().events().delete(calendarId=booking.master.google_calendar_id, eventId=booking.google_event_id).execute
        )
    except Exception:
        log.exception("Google Calendar: не вдалося видалити подію %s", booking.google_event_id)
