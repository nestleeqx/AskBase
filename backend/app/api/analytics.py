"""Аналитика бота за неделю: сколько диалогов, какая доля вопросов с ответом, о чём спрашивают.

Считается по диалогам в Telegram: вымышленные демо-диалоги и свой подключённый чат гостя.
Тестовый чат в админке — проверка бота, а не клиенты, поэтому в статистику не входит.
"""

import statistics
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import SessionDep, ViewerDep
from app.models import DEMO_VISITOR, Booking, Conversation, Message, now
from app.services.prompts import TOPICS

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

DAYS = 7
UNANSWERED = ("no_match", "not_in_docs", "no_sources", "error")
# Ответы бота на вопрос клиента: из них считается доля «с ответом»
QUESTION_REASONS = ("answered", *UNANSWERED)
# Ответы бота на любое обращение клиента — для тем: вопросы, запись, просьба о человеке
TOPIC_REASONS = (
    *QUESTION_REASONS,
    "booking_intent",
    "booking",
    "my_booking",
    "cancel_booking",
    "operator",
)


class Day(BaseModel):
    date: date
    dialogs: int
    questions: int
    answered: int


class Topic(BaseModel):
    topic: str
    label: str
    count: int


class Analytics(BaseModel):
    days: list[Day]
    dialogs: int
    questions: int
    answered: int
    # Доля вопросов, на которые бот ответил сам: 0..1
    answered_share: float | None
    median_ms: int | None
    bookings: int
    operator_requests: int
    unanswered: int
    topics: list[Topic]
    timezone: str


@router.get("", response_model=Analytics)
async def analytics(session: SessionDep, viewer: ViewerDep):
    tz = ZoneInfo(get_settings().clinic_timezone)
    today = now().astimezone(tz).date()
    first = today - timedelta(days=DAYS - 1)
    since = datetime.combine(first, datetime.min.time(), tzinfo=tz)
    # Владелец видит всех клиентов, гость — демо-диалоги и свой чат
    visible = (
        (Conversation.channel == "telegram",)
        if viewer.owner
        else (
            Conversation.channel == "telegram",
            Conversation.visitor_id.in_([viewer.visitor, DEMO_VISITOR]),
        )
    )

    rows = (
        await session.execute(
            select(
                Message.conversation_id,
                Message.role,
                Message.reason,
                Message.topic,
                Message.latency_ms,
                Message.created_at,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*visible, Message.created_at >= since)
        )
    ).all()

    per_day = {first + timedelta(days=i): {"dialogs": set(), "q": 0, "a": 0} for i in range(DAYS)}
    dialogs: set[str] = set()
    topics: Counter[str] = Counter()
    latencies: list[int] = []
    questions = answered = unanswered = operator = 0
    for conv_id, role, reason, topic, latency, created in rows:
        day = per_day.get(created.astimezone(tz).date())
        if role == "user":
            dialogs.add(conv_id)
            if day:
                day["dialogs"].add(conv_id)
            continue
        if role != "bot":
            continue
        if reason in QUESTION_REASONS:
            questions += 1
            if day:
                day["q"] += 1
            if reason == "answered":
                answered += 1
                if day:
                    day["a"] += 1
                if latency:
                    latencies.append(latency)
            else:
                unanswered += 1
        elif reason == "operator":
            operator += 1
        if reason in TOPIC_REASONS and topic:
            topics[topic] += 1

    bookings = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .join(Conversation, Conversation.id == Booking.conversation_id)
        .where(*visible, Booking.created_at >= since)
    )
    return Analytics(
        days=[
            Day(date=d, dialogs=len(v["dialogs"]), questions=v["q"], answered=v["a"])
            for d, v in per_day.items()
        ],
        dialogs=len(dialogs),
        questions=questions,
        answered=answered,
        answered_share=answered / questions if questions else None,
        median_ms=round(statistics.median(latencies)) if latencies else None,
        bookings=bookings or 0,
        operator_requests=operator,
        unanswered=unanswered,
        topics=[Topic(topic=t, label=TOPICS.get(t, t), count=c) for t, c in topics.most_common(10)],
        timezone=get_settings().clinic_timezone,
    )
