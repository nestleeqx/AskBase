import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.deps import RedisDep, SessionDep, VisitorDep
from app.models import Conversation
from app.schemas import TelegramLink, TelegramStatus
from app.services.bot import bot_username, create_link_token
from app.services.telegram import TelegramError, get_telegram

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
log = logging.getLogger(__name__)

NOT_READY = "Telegram-бот сейчас недоступен. Попробуйте позже."


@router.get("", response_model=TelegramStatus)
async def status(session: SessionDep, visitor: VisitorDep, redis: RedisDep):
    tg = get_telegram()
    if tg is None:
        return TelegramStatus(enabled=False)
    try:
        username = await bot_username(redis, tg)
    except TelegramError as e:
        log.warning("Telegram: %s", e)
        return TelegramStatus(enabled=False)
    linked = await session.scalar(
        select(Conversation.id)
        .where(Conversation.visitor_id == visitor, Conversation.channel == "telegram")
        .limit(1)
    )
    return TelegramStatus(
        enabled=True,
        username=username,
        linked=linked is not None,
        manager=bool(get_settings().manager_chat_id),
    )


@router.post("/link", response_model=TelegramLink)
async def link(visitor: VisitorDep, redis: RedisDep):
    """Ссылка на бота с одноразовым токеном: по ней чат привяжется к посетителю."""
    tg = get_telegram()
    if tg is None:
        raise HTTPException(503, NOT_READY)
    try:
        username = await bot_username(redis, tg)
    except TelegramError as e:
        log.warning("Telegram: %s", e)
        raise HTTPException(503, NOT_READY) from None
    token = await create_link_token(redis, visitor)
    return TelegramLink(url=f"https://t.me/{username}?start={token}")
