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
MAX_REASON = 300
MAX_TIME = 200

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


def next_step(state: dict[str, Any]) -> str | None:
    """Первый шаг, на который клиент ещё не ответил. Пропущенный повод — тоже ответ."""
    return next((step for step in STEPS if step not in state), None)


def from_draft(draft: dict[str, str]) -> tuple[dict[str, Any], str | None]:
    """Что клиент написал сам, когда попросил записать его, — в ответы на шаги записи.

    Нейросеть переносит слова клиента как есть, поэтому каждое поле проверяется так же,
    как ответ на шаге. Второе значение — номер, в котором не хватает цифр: бот переспросит.
    """
    state: dict[str, Any] = {}
    name = valid_name(draft.get("name", ""))
    if name:
        state["name"] = name
    raw_phone = clean(draft.get("phone", ""))
    phone = normalize_phone(raw_phone) if raw_phone else None
    if phone:
        state["phone"] = phone
    reason = clean(draft.get("reason", ""))
    if reason:
        state["reason"] = reason[:MAX_REASON]
    time = clean(draft.get("preferred_time", ""))
    if time:
        state["time"] = time[:MAX_TIME]
    # Переспрашиваем про номер, только если клиент его правда писал — с цифрами
    bad = raw_phone if raw_phone and not phone and re.search(r"\d", raw_phone) else None
    return state, bad


_TIME_FILLER = re.compile(r"\b(на|в|во|к)\b|[^\w:]", re.IGNORECASE)


def same_time(a: str, b: str) -> bool:
    """«на завтра на 12:30» и «завтра в 12:30» — одно и то же время, а не перенос."""

    def norm(text: str) -> str:
        return " ".join(_TIME_FILLER.sub(" ", text.lower().replace("ё", "е")).split())

    return bool(a) and norm(a) == norm(b)


def changes(state: dict[str, Any], old: Any) -> bool:
    """Меняет ли написанное клиентом (имя, телефон, повод, время) его прежнюю заявку."""
    if "time" in state and not same_time(state["time"], old.preferred_time):
        return True
    current = {"name": old.name, "phone": old.phone, "reason": old.reason}
    return any(key in state and state[key] != value for key, value in current.items())
