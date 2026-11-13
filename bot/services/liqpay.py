"""Посилання на оплату LiqPay (Checkout API) і перевірка callback-підпису.

Формат: data = base64(json), signature = base64(sha1(private_key + data + private_key)).
"""

import base64
import hashlib
import json

from ..config import settings

CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"


def _sign(data: str) -> str:
    raw = (settings.liqpay_private_key + data + settings.liqpay_private_key).encode()
    return base64.b64encode(hashlib.sha1(raw).digest()).decode()


def payment_link(booking_id: int, amount: int, description: str) -> str:
    params = {
        "version": 3,
        "public_key": settings.liqpay_public_key,
        "action": "pay",
        "amount": amount,
        "currency": "UAH",
        "description": description,
        "order_id": f"booking-{booking_id}",
        "server_url": f"{settings.public_url}/liqpay/callback",
        "language": "uk",
    }
    data = base64.b64encode(json.dumps(params).encode()).decode()
    return f"{CHECKOUT_URL}?data={data}&signature={_sign(data)}"


def parse_callback(data: str, signature: str) -> dict:
    """Повертає розшифровані дані або кидає ValueError, якщо підпис не збігся."""
    if _sign(data) != signature:
        raise ValueError("Невірний підпис LiqPay")
    return json.loads(base64.b64decode(data))


def prepayment_for(price: int) -> int:
    if price < settings.prepay_from or not settings.liqpay_public_key:
        return 0
    return round(price * settings.prepay_percent / 100)
