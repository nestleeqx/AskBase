import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.deps import RedisDep, SessionDep, VisitorDep
from app.models import Conversation
from app.schemas import TelegramLink, TelegramStatus
from app.services.bot import Bot, bot_username, create_link_token, ensure_webhook
from app.services.telegram import TelegramError, get_telegram

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
log = logging.getLogger(__name__)

NOT_READY = "Telegram-бот сейчас недоступен. Попробуйте позже."


@router.get("", response_model=TelegramStatus)
async def status(request: Request, session: SessionDep, visitor: VisitorDep, redis: RedisDep):
    tg = get_telegram()
    if tg is None:
        return TelegramStatus(enabled=False)
    try:
        username = await bot_username(redis, tg)
        # Заодно на Vercel ставим вебхук: статус запрашивают лендинг и раздел «Диалоги»
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        await ensure_webhook(redis, tg, host)
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


@router.post("/webhook")
async def webhook(
    request: Request,
    redis: RedisDep,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Обновления от Telegram на Vercel. Секрет в заголовке отличает их от чужих запросов."""
    tg = get_telegram()
    secret = get_settings().telegram_webhook_secret
    if tg is None or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", secret):
        raise HTTPException(403, "Нет доступа")
    update = await request.json()
    # Ошибку разбора одного сообщения не возвращаем Telegram: иначе он будет слать его снова.
    # Bot.handle сам ловит ошибки и вежливо отвечает клиенту
    bot = Bot(SessionLocal, request.app.state.llm, request.app.state.embedder, redis, tg)
    await bot.handle(update)
    return {"ok": True}
