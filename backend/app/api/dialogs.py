"""Диалоги Telegram в админке: история, ответ администратора, заявки на запись.

Посетитель видит вымышленные демо-диалоги и свои настоящие — из чата, который он привязал
кнопкой «Подключить Telegram». Менять можно только свои.
"""

import logging
from datetime import timedelta
from html import escape

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import message_out
from app.config import get_settings
from app.deps import RedisDep, SessionDep, Viewer, ViewerDep
from app.models import DEMO_VISITOR, Booking, Conversation, Message, TelegramChat, now
from app.schemas import (
    BookingList,
    BookingOut,
    BookingPatch,
    DialogDetail,
    DialogLast,
    DialogList,
    DialogSummary,
    ReplyIn,
)
from app.services.redis_store import hit_limit
from app.services.telegram import TelegramError, get_telegram

router = APIRouter(prefix="/api", tags=["dialogs"])
log = logging.getLogger(__name__)

NOT_FOUND = "Диалог не найден."
DEMO_READONLY = (
    "Это пример диалога — в нём ответить нельзя. Подключите свой Telegram и напишите боту: "
    "свой диалог появится в списке."
)
SEND_FAILED = "Не удалось отправить сообщение в Telegram. Попробуйте ещё раз."
# Сколько сообщений переписки отдаём за раз
PAGE = 50
BOT_BACK = (
    "Снова на связи бот клиники. Если понадобится администратор — нажмите "
    "«Связаться с администратором»."
)


def _visible(viewer: Viewer):
    """Гость видит демо-диалоги и свой чат, владелец — все диалоги клиники."""
    if viewer.owner:
        return Conversation.channel == "telegram"
    return Conversation.visitor_id.in_([viewer.visitor, DEMO_VISITOR])


def _can_change(viewer: Viewer, owner_id: str | None) -> bool:
    """Демо-диалоги и демо-заявки не меняет никто; владелец — всё остальное, гость — своё."""
    if owner_id == DEMO_VISITOR:
        return False
    return viewer.owner or owner_id == viewer.visitor


def _active_until(conv: Conversation):
    return conv.operator_until if conv.operator_until and conv.operator_until > now() else None


def _summary(conv: Conversation, chat: TelegramChat, count: int, last: Message | None) -> dict:
    return {
        "id": conv.id,
        "title": chat.title,
        "username": chat.username,
        "demo": conv.visitor_id == DEMO_VISITOR,
        "waiting_since": conv.waiting_since,
        "attention_at": conv.attention_at,
        "operator_until": _active_until(conv),
        "updated_at": conv.updated_at,
        "messages_count": count,
        "last": DialogLast(role=last.role, text=last.text, created_at=last.created_at)
        if last
        else None,
    }


def _booking_out(b: Booking, client: str, demo: bool) -> BookingOut:
    return BookingOut(
        id=b.id,
        conversation_id=b.conversation_id,
        client=client,
        name=b.name,
        phone=b.phone,
        reason=b.reason,
        preferred_time=b.preferred_time,
        status=b.status,
        created_at=b.created_at,
        client_changed_at=b.client_changed_at or b.created_at,
        demo=demo,
    )


async def _dialog(
    session: AsyncSession, conversation_id: str, viewer: Viewer
) -> tuple[Conversation, TelegramChat]:
    row = (
        await session.execute(
            select(Conversation, TelegramChat)
            .join(TelegramChat, TelegramChat.conversation_id == Conversation.id)
            .where(Conversation.id == conversation_id, _visible(viewer))
        )
    ).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


async def _own_dialog(
    session: AsyncSession, conversation_id: str, viewer: Viewer
) -> tuple[Conversation, TelegramChat]:
    conv, chat = await _dialog(session, conversation_id, viewer)
    if not _can_change(viewer, conv.visitor_id):
        raise HTTPException(403, DEMO_READONLY)
    return conv, chat


@router.get("/dialogs", response_model=DialogList)
async def dialogs(
    session: SessionDep,
    viewer: ViewerDep,
    q: str = Query("", max_length=100),
    waiting: bool = False,
):
    query = (
        select(Conversation, TelegramChat)
        .join(TelegramChat, TelegramChat.conversation_id == Conversation.id)
        .where(_visible(viewer))
    )
    words = q.strip()
    if words:
        pattern = "%" + words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                TelegramChat.title.ilike(pattern),
                TelegramChat.username.ilike(pattern),
                exists().where(
                    Message.conversation_id == Conversation.id, Message.text.ilike(pattern)
                ),
            )
        )
    rows = (await session.execute(query)).all()

    ids = [conv.id for conv, _ in rows]
    counts = dict(
        (
            await session.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(ids))
                .group_by(Message.conversation_id)
            )
        ).all()
    )
    lasts = {
        m.conversation_id: m
        for m in await session.scalars(
            select(Message).where(
                Message.id.in_(
                    select(func.max(Message.id))
                    .where(Message.conversation_id.in_(ids))
                    .group_by(Message.conversation_id)
                )
            )
        )
    }
    items = [
        DialogSummary(**_summary(conv, chat, counts.get(conv.id, 0), lasts.get(conv.id)))
        for conv, chat in rows
    ]
    total_waiting = sum(1 for d in items if d.waiting_since)
    if waiting:
        items = [d for d in items if d.waiting_since]
    # Сначала те, кто ждёт человека, затем по свежести
    items.sort(key=lambda d: (d.waiting_since is None, -d.updated_at.timestamp()))
    return DialogList(dialogs=items, waiting=total_waiting)


@router.get("/dialogs/{conversation_id}", response_model=DialogDetail)
async def dialog(
    conversation_id: str,
    session: SessionDep,
    viewer: ViewerDep,
    before: int | None = Query(None, ge=1),
    limit: int = Query(PAGE, ge=1, le=1000),
):
    """Переписка страницами: последние limit сообщений, а с before — те, что раньше него.
    Длинный диалог не грузится целиком: ранние сообщения админка подгружает при прокрутке вверх."""
    conv, chat = await _dialog(session, conversation_id, viewer)
    in_dialog = Message.conversation_id == conv.id
    page_query = select(Message).where(in_dialog)
    if before is not None:
        page_query = page_query.where(Message.id < before)
    page = list(await session.scalars(page_query.order_by(Message.id.desc()).limit(limit)))
    page.reverse()
    has_more = bool(page) and bool(
        await session.scalar(select(exists().where(in_dialog, Message.id < page[0].id)))
    )
    total = await session.scalar(select(func.count()).where(in_dialog)) or 0
    last = await session.scalar(
        select(Message).where(in_dialog).order_by(Message.id.desc()).limit(1)
    )
    bookings = await session.scalars(
        select(Booking).where(Booking.conversation_id == conv.id).order_by(Booking.created_at)
    )
    demo = conv.visitor_id == DEMO_VISITOR
    return DialogDetail(
        **_summary(conv, chat, total, last),
        messages=[message_out(m) for m in page],
        has_more=has_more,
        bookings=[_booking_out(b, chat.title, demo) for b in bookings],
    )


@router.post("/dialogs/{conversation_id}/reply", response_model=DialogDetail)
async def reply(
    conversation_id: str, body: ReplyIn, session: SessionDep, redis: RedisDep, viewer: ViewerDep
):
    """Ответ администратора: уходит клиенту в Telegram, бот в этом чате замолкает."""
    s = get_settings()
    conv, chat = await _own_dialog(session, conversation_id, viewer)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Напишите ответ.")
    tg = get_telegram()
    if tg is None:
        raise HTTPException(503, "Telegram-бот сейчас недоступен. Попробуйте позже.")
    await hit_limit(redis, "reply", viewer.visitor, s.questions_per_hour)
    try:
        await tg.send(chat.chat_id, f"<b>Администратор клиники:</b>\n{escape(text)}")
    except TelegramError as e:
        log.warning("Ответ администратора не отправлен: %s", e)
        raise HTTPException(502, SEND_FAILED) from None

    session.add(Message(conversation_id=conv.id, role="operator", text=text))
    conv.updated_at = now()
    conv.waiting_since = None
    conv.operator_until = now() + timedelta(minutes=s.operator_minutes)
    await session.commit()
    return await dialog(conversation_id, session, viewer, before=None, limit=PAGE)


@router.post("/dialogs/{conversation_id}/release", response_model=DialogDetail)
async def release(conversation_id: str, session: SessionDep, viewer: ViewerDep):
    """«Вернуть боту»: бот снова отвечает клиенту сам."""
    conv, chat = await _own_dialog(session, conversation_id, viewer)
    was_active = _active_until(conv) is not None
    conv.operator_until = None
    conv.waiting_since = None
    await session.commit()
    tg = get_telegram()
    if was_active and tg is not None:
        try:
            await tg.send(chat.chat_id, BOT_BACK)
        except TelegramError as e:
            log.warning("Telegram: %s", e)
    return await dialog(conversation_id, session, viewer, before=None, limit=PAGE)


@router.get("/bookings", response_model=BookingList)
async def bookings(session: SessionDep, viewer: ViewerDep):
    rows = (
        await session.execute(
            select(Booking, TelegramChat.title, Conversation.visitor_id)
            .join(Conversation, Conversation.id == Booking.conversation_id)
            .join(TelegramChat, TelegramChat.conversation_id == Conversation.id)
            .where(_visible(viewer))
            .order_by(Booking.created_at.desc())
        )
    ).all()
    items = [_booking_out(b, title, owner == DEMO_VISITOR) for b, title, owner in rows]
    return BookingList(bookings=items, new=sum(1 for b in items if b.status == "new"))


@router.patch("/bookings/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: str, body: BookingPatch, session: SessionDep, viewer: ViewerDep
):
    row = (
        await session.execute(
            select(Booking, TelegramChat.title, Conversation.visitor_id)
            .join(Conversation, Conversation.id == Booking.conversation_id)
            .join(TelegramChat, TelegramChat.conversation_id == Conversation.id)
            .where(Booking.id == booking_id, _visible(viewer))
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Заявка не найдена.")
    b, title, owner = row
    if not _can_change(viewer, owner):
        raise HTTPException(403, "Это пример заявки — её статус менять нельзя.")
    b.status = body.status
    await session.commit()
    return _booking_out(b, title, False)
