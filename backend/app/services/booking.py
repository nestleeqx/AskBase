"""Запись на приём в Telegram по шагам: имя → телефон → повод → удобное время.

Шаг и ответы клиента хранятся в Redis час: если клиент отвлёкся, запись начнётся заново.
"""

import json
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from app.config import get_settings
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


_MONTHS = (
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
)
_RELATIVE_DAYS = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
_RELATIVE = re.compile(r"\b(сегодня|послезавтра|завтра)\b", re.IGNORECASE)
# «в субботу» → «в субботу, 1 ноября»; уже с датой («в субботу, 1 ноября») не трогаем
_WEEKDAYS = ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье")
_WEEKDAY = re.compile(r"\b(в|во)\s+(" + "|".join(_WEEKDAYS) + r")\b(?!,?\s*\d)", re.IGNORECASE)


def _day(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]}"


def clinic_today() -> date:
    return datetime.now(ZoneInfo(get_settings().clinic_timezone)).date()


def pin_dates(text: str, today: date | None = None) -> str:
    """«завтра в 12:30» → «30 октября в 12:30»: заявка хранится с датой, и через день
    в админке не висит «завтра». Дни недели — ближайший такой день после сегодняшнего."""
    today = today or clinic_today()
    text = _RELATIVE.sub(lambda m: _day(today + timedelta(days=_RELATIVE_DAYS[m[1].lower()])), text)

    def weekday(m: re.Match[str]) -> str:
        ahead = (_WEEKDAYS.index(m[2].lower()) - today.weekday()) % 7 or 7
        return f"{m[0]}, {_day(today + timedelta(days=ahead))}"

    return _WEEKDAY.sub(weekday, text)


def time_buttons(today: date | None = None) -> list[list[str]]:
    """Готовые ответы на «Когда удобно?» — сразу с днём: голое «Днём» администратору ничего
    не говорит. В воскресенье клиника закрыта — тогда предлагаем понедельник."""
    tomorrow = (today or clinic_today()) + timedelta(days=1)
    day = "В понедельник" if tomorrow.weekday() == 6 else "Завтра"
    return [[f"{day} утром", f"{day} днём"], [f"{day} вечером", "В ближайшее время"]]


_TIME_FILLER = re.compile(r"\b(на|в|во|к)\b|[^\w:]", re.IGNORECASE)


def same_time(a: str, b: str) -> bool:
    """«на завтра на 12:30» и «30 октября в 12:30» (так «завтра» сохранено) — одно и то же время,
    а не перенос."""

    def norm(text: str) -> str:
        text = pin_dates(text).lower().replace("ё", "е")
        return " ".join(_TIME_FILLER.sub(" ", text).split())

    return bool(a) and norm(a) == norm(b)


def changes(state: dict[str, Any], old: Any) -> bool:
    """Меняет ли написанное клиентом (имя, телефон, повод, время) его прежнюю заявку."""
    if "time" in state and not same_time(state["time"], old.preferred_time):
        return True
    current = {"name": old.name, "phone": old.phone, "reason": old.reason}
    return any(key in state and state[key] != value for key, value in current.items())
