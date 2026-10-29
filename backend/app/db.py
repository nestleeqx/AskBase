from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
# В serverless каждый вызов функции живёт недолго — держать пул соединений бессмысленно
engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    **({"poolclass": NullPool} if _settings.vercel else {}),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


# create_all создаёт только новые таблицы — колонки, добавленные в уже существующие,
# досоздаются здесь. Каждая команда безопасна при повторном запуске
MIGRATIONS = [
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS waiting_since TIMESTAMPTZ",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS operator_until TIMESTAMPTZ",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS client_changed_at TIMESTAMPTZ",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS attention_at TIMESTAMPTZ",
]


async def init_db() -> None:
    from app import models  # noqa: F401  — регистрирует таблицы в metadata

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for sql in MIGRATIONS:
            await conn.execute(text(sql))
