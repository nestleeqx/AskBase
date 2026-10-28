"""Запись на приём в Telegram по шагам: имя → телефон → повод → удобное время.

Шаг и ответы клиента хранятся в Redis час: если клиент отвлёкся, запись начнётся заново.
"""

import json
import re
from typing import Any

from redis.asyncio import Redis

from app.services.redis_store import PREFIX

STEPS = ("name", "phone", "reason", "time")
STATE_TTL = 3600

_LETTER = re.compile(r"[a-zа-яё]", re.IGNORECASE)


def _key(chat_id: int) -> str:
    return f"{PREFIX}tg:booking:{chat_id}"


async def get_state(redis: Redis, chat_id: int) -> dict[str, Any] | None:
    raw = await redis.get(_key(chat_id))
    return json.loads(raw) if raw else None


async def save_state(redis: Redis, chat_id: int, state: dict[str, Any]) -> None:
    await redis.set(_key(chat_id), json.dumps(state, ensure_ascii=False), ex=STATE_TTL)


async def clear_state(redis: Redis, chat_id: int) -> bool:
    """True — запись была начата и теперь отменена."""
    return bool(await redis.delete(_key(chat_id)))


def clean(text: str) -> str:
    return " ".join(text.split())


def valid_name(text: str) -> str | None:
    name = clean(text)
    if not 2 <= len(name) <= 60 or name.startswith("/") or not _LETTER.search(name):
        return None
    return name


def normalize_phone(text: str) -> str | None:
    """Российский номер → +7 (900) 123-45-67; иностранный с «+» — цифрами как есть."""
    if _LETTER.search(text):
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":
        d = digits[1:]
        return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
    if 11 <= len(digits) <= 15 and text.strip().startswith("+"):
        return "+" + digits
    return None
