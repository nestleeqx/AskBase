"""«Бот не смог ответить»: вопросы, на которые в базе не нашлось ответа.

Из них владелец понимает, чего не хватает в документах. Ответ можно дописать прямо здесь —
он попадёт в документ «Ответы администратора», и бот начнёт отвечать на такой вопрос сам.
Вымышленные демо-вопросы гость тоже может разобрать: отметка хранится только для него.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import EmbedderDep, RedisDep, SessionDep, Viewer, ViewerDep
from app.models import (
    CLINIC_OWNER,
    DEMO_VISITOR,
    Conversation,
    KbAnswer,
    Message,
    TelegramChat,
    now,
)
from app.services.answer import REASONS
from app.services.kb_answers import add_answer
from app.services.redis_store import PREFIX

router = APIRouter(prefix="/api/unanswered", tags=["unanswered"])

# Бот не ответил сам: в базе нет ответа или сервис был недоступен. Просьбы позвать
# администратора и запись сюда не попадают — это не пробелы в базе знаний
UNANSWERED = ("no_match", "not_in_docs", "no_sources", "error")
DEMO_TTL = 30 * 24 * 3600
NOT_FOUND = "Вопрос не найден."
ADD_FAILED = "Не удалось добавить ответ в базу. Попробуйте ещё раз."


class UnansweredItem(BaseModel):
    id: int
    question: str
    reason: str
    reason_label: str
    channel: str
    conversation_id: str
    client: str
    created_at: datetime
    demo: bool
    resolved: bool
    # Ответ администратора, добавленный в базу знаний
    kb_answer: str | None


class UnansweredList(BaseModel):
    items: list[UnansweredItem]
    open: int
    resolved: int


class ResolveIn(BaseModel):
    resolved: bool = True


class AnswerIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=3, max_length=2000)


def _demo_key(visitor: str) -> str:
    return f"{PREFIX}resolved:{visitor}"


def _visible(viewer: Viewer):
    """Telegram — свои и демо-диалоги (владелец — все), тестовый чат — только свой."""
    telegram = Conversation.channel == "telegram"
    if not viewer.owner:
        telegram = and_(telegram, Conversation.visitor_id.in_([viewer.visitor, DEMO_VISITOR]))
    return or_(
        telegram, and_(Conversation.channel == "test", Conversation.visitor_id == viewer.visitor)
    )


async def _items(
    session: AsyncSession, redis, viewer: Viewer, message_id: int | None = None
) -> list[UnansweredItem]:
    query = (
        select(Message, Conversation, TelegramChat.title)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .outerjoin(TelegramChat, TelegramChat.conversation_id == Conversation.id)
        .where(
            Message.role == "bot",
            Message.answered.is_(False),
            Message.reason.in_(UNANSWERED),
            _visible(viewer),
        )
        .order_by(Message.id.desc())
        .limit(200)
    )
    if message_id is not None:
        query = query.where(Message.id == message_id)
    rows = (await session.execute(query)).all()
    if not rows:
        return []

    # Вопрос клиента — последнее его сообщение перед ответом бота
    conv_ids = {conv.id for _, conv, _ in rows}
    questions: dict[str, list[tuple[int, str]]] = {}
    for mid, cid, text in (
        await session.execute(
            select(Message.id, Message.conversation_id, Message.text)
            .where(Message.conversation_id.in_(conv_ids), Message.role == "user")
            .order_by(Message.id)
        )
    ).all():
        questions.setdefault(cid, []).append((mid, text))
    answers = {
        a.message_id: a.answer
        for a in await session.scalars(
            select(KbAnswer).where(
                KbAnswer.visitor_id.in_([viewer.visitor, CLINIC_OWNER]),
                KbAnswer.message_id.in_([m.id for m, _, _ in rows]),
            )
        )
    }
    demo_resolved = await redis.smembers(_demo_key(viewer.visitor))

    items = []
    for m, conv, title in rows:
        before = [text for mid, text in questions.get(conv.id, []) if mid < m.id]
        demo = conv.visitor_id == DEMO_VISITOR
        items.append(
            UnansweredItem(
                id=m.id,
                question=before[-1] if before else "",
                reason=m.reason,
                reason_label=REASONS[m.reason],
                channel=conv.channel,
                conversation_id=conv.id,
                client=title or "Тестовый чат",
                created_at=m.created_at,
                demo=demo,
                resolved=str(m.id) in demo_resolved if demo else m.resolved_at is not None,
                kb_answer=answers.get(m.id),
            )
        )
    return items


async def _one(session: AsyncSession, redis, viewer: Viewer, message_id: int) -> UnansweredItem:
    items = await _items(session, redis, viewer, message_id)
    if not items:
        raise HTTPException(404, NOT_FOUND)
    return items[0]


async def _set_resolved(
    session: AsyncSession, redis, viewer: Viewer, item: UnansweredItem, resolved: bool
) -> None:
    if item.demo:
        key = _demo_key(viewer.visitor)
        if resolved:
            await redis.sadd(key, str(item.id))
            await redis.expire(key, DEMO_TTL)
        else:
            await redis.srem(key, str(item.id))
        return
    message = await session.get(Message, item.id)
    message.resolved_at = now() if resolved else None
    await session.commit()


@router.get("", response_model=UnansweredList)
async def unanswered(
    session: SessionDep,
    redis: RedisDep,
    viewer: ViewerDep,
    status: Literal["open", "resolved", "all"] = Query("open"),
):
    items = await _items(session, redis, viewer)
    opened = sum(1 for i in items if not i.resolved)
    total = len(items)
    if status != "all":
        items = [i for i in items if i.resolved == (status == "resolved")]
    return UnansweredList(items=items, open=opened, resolved=total - opened)


@router.post("/{message_id}/resolve", response_model=UnansweredItem)
async def resolve(
    message_id: int, body: ResolveIn, session: SessionDep, redis: RedisDep, viewer: ViewerDep
):
    item = await _one(session, redis, viewer, message_id)
    await _set_resolved(session, redis, viewer, item, body.resolved)
    return await _one(session, redis, viewer, message_id)


@router.post("/{message_id}/answer", response_model=UnansweredItem)
async def answer(
    message_id: int,
    body: AnswerIn,
    session: SessionDep,
    redis: RedisDep,
    embedder: EmbedderDep,
    viewer: ViewerDep,
):
    """Ответ администратора — в базу знаний: бот начнёт отвечать на такой вопрос сам."""
    item = await _one(session, redis, viewer, message_id)
    doc = await add_answer(
        session,
        embedder,
        viewer.profile_key,
        " ".join(body.question.split()),
        body.answer.strip(),
        message_id,
    )
    if doc.status != "ready":
        raise HTTPException(502, doc.error or ADD_FAILED)
    await _set_resolved(session, redis, viewer, item, True)
    return await _one(session, redis, viewer, message_id)
