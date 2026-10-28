"""Вымышленные демо-диалоги в разделе «Диалоги»: их видят все посетители, менять нельзя.

Тексты и ответы бота — в app/seed/demo-dialogs.json (собирает scripts/build_demo_dialogs.py).
Время сообщений отсчитывается от запуска: диалоги выглядят свежими.
"""

import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import (
    DEMO_VISITOR,
    Booking,
    Conversation,
    Document,
    Message,
    TelegramChat,
    now,
)

log = logging.getLogger(__name__)

DEMO_FILE = Path(__file__).resolve().parents[1] / "seed" / "demo-dialogs.json"
# Увеличьте, если поменялся demo-dialogs.json, — диалоги пересоздадутся при следующем запуске
VERSION = 2
REFRESH_HOURS = 24


def _id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"askbase-demo-dialog-{VERSION}-{key}"))


async def ensure_demo_dialogs(sessions: async_sessionmaker) -> None:
    if not DEMO_FILE.exists():
        return
    data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    dialogs = data["dialogs"]
    async with sessions() as session:
        if not dialogs:
            return
        first = await session.get(Conversation, _id(dialogs[0]["key"]))
        # Демо-диалоги на месте и не устарели. Раз в сутки они пересоздаются — иначе
        # «вчера» в списке и аналитика за неделю со временем опустели бы
        fresh_since = now() - timedelta(hours=dialogs[0]["hours_ago"] + REFRESH_HOURS)
        if first is not None and first.created_at > fresh_since:
            return
        # Прежняя или устаревшая версия демо-диалогов — удаляем вместе с сообщениями и заявками
        await session.execute(delete(Conversation).where(Conversation.visitor_id == DEMO_VISITOR))
        doc_ids = {
            d.seed_key: d.id
            for d in await session.scalars(select(Document).where(Document.seed_key.is_not(None)))
        }
        start = now()
        for i, d in enumerate(dialogs):
            base = start - timedelta(hours=d["hours_ago"])

            def at(minute: float, base=base):
                return base + timedelta(minutes=minute)

            conv = Conversation(id=_id(d["key"]), visitor_id=DEMO_VISITOR, channel="telegram")
            waiting = None
            for m in d["messages"]:
                if m["role"] == "operator":
                    waiting = None
                elif m.get("answered") is False or m.get("reason") == "operator":
                    waiting = waiting or at(m["minute"])
            conv.created_at = at(0)
            conv.updated_at = at(d["messages"][-1]["minute"])
            conv.waiting_since = waiting
            session.add(conv)
            # Сначала диалог: у чата и заявок нет связи с ним в ORM, порядок вставки задаём сами
            await session.flush()
            # Отрицательные id не совпадут с настоящими чатами клиентов
            session.add(
                TelegramChat(
                    chat_id=-(1000 + i),
                    conversation_id=conv.id,
                    title=d["title"],
                    username=d["username"],
                    created_at=at(0),
                )
            )
            for m in d["messages"]:
                trace = m.get("trace")
                if trace:
                    for hit in trace["hits"]:
                        hit["document"]["id"] = doc_ids.get(hit["document"]["id"], "")
                session.add(
                    Message(
                        conversation_id=conv.id,
                        role=m["role"],
                        text=m["text"],
                        answered=m.get("answered"),
                        reason=m.get("reason"),
                        topic=m.get("topic"),
                        sources=[
                            {**s, "id": doc_ids.get(s["id"], "")} for s in m.get("sources", [])
                        ],
                        trace=trace,
                        latency_ms=m.get("latency_ms"),
                        created_at=at(m["minute"]),
                    )
                )
            for b in d["bookings"]:
                session.add(
                    Booking(
                        conversation_id=conv.id,
                        name=b["name"],
                        phone=b["phone"],
                        reason=b["reason"],
                        preferred_time=b["preferred_time"],
                        status=b["status"],
                        created_at=at(b["minute"]),
                    )
                )
        try:
            await session.commit()
        except IntegrityError:
            # Параллельный запуск (несколько функций Vercel) уже создал диалоги
            await session.rollback()
            return
    log.info("Демо-диалоги: %d", len(dialogs))
