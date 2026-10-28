import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import (
    analytics,
    chat,
    dialogs,
    documents,
    misc,
    search,
    settings,
    telegram,
    unanswered,
)
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.embeddings import create_embedder
from app.llm import create_provider
from app.services.demo_dialogs import ensure_demo_dialogs
from app.services.redis_store import RateLimitExceeded, get_redis
from app.services.seed import ensure_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

LIMIT_MESSAGES = {
    "search": "Лимит демо: {limit} поисков в час",
    "upload": "Лимит демо: {limit} загрузок в час",
    "chat": "Лимит демо: {limit} вопросов в час",
    "reply": "Лимит демо: {limit} ответов в час",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    app.state.embedder = create_embedder(settings)
    app.state.llm = create_provider(settings)
    await ensure_seed(SessionLocal, app.state.embedder, get_redis())
    await ensure_demo_dialogs(SessionLocal)
    yield
    await app.state.embedder.aclose()
    await app.state.llm.aclose()


app = FastAPI(title="AskBase API", version="0.1.0", lifespan=lifespan)


async def catch_unhandled(request: Request, call_next):
    """Непойманная ошибка → понятный JSON 500.

    Без этого ответ 500 уходит мимо CORS, браузер его блокирует, и пользователь видит
    «не удалось связаться с сервером» вместо сообщения об ошибке. Подключено до CORS,
    поэтому оказывается внутри него и ответ получает CORS-заголовки.
    """
    try:
        return await call_next(request)
    except Exception:
        log.exception("Необработанная ошибка: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Что-то пошло не так. Попробуйте ещё раз через минуту."},
        )


app.add_middleware(BaseHTTPMiddleware, dispatch=catch_unhandled)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=get_settings().cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "Content-Disposition"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(_: Request, exc: RateLimitExceeded):
    minutes = max(1, exc.retry_after // 60)
    message = LIMIT_MESSAGES.get(exc.scope, "Лимит запросов").format(limit=exc.limit)
    return JSONResponse(
        status_code=429,
        content={"detail": f"{message}. Попробуйте через {minutes} мин."},
        headers={"Retry-After": str(exc.retry_after)},
    )


app.include_router(misc.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(dialogs.router)
app.include_router(telegram.router)
app.include_router(unanswered.router)
app.include_router(analytics.router)
app.include_router(settings.router)
