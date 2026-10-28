"""Тесты API идут на настоящем Postgres с pgvector — том же, что в docker compose
(порт 5434), в отдельной базе askbase_test. Без Postgres эти тесты пропускаются,
а тесты разбора файлов и нарезки работают и так."""

import os

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://askbase:askbase@localhost:5434/askbase_test"
)
os.environ.update(
    DATABASE_URL=TEST_DB,
    EMBEDDING_PROVIDER="mock",
    SEARCHES_PER_HOUR="1000",
    UPLOADS_PER_HOUR="1000",
    SITE_URL="https://clinic.example",
    # Ключ из .env разработчика не должен попасть в тесты: они не ходят во внешние API
    OPENAI_API_KEY="",
)

import asyncpg  # noqa: E402
import fakeredis  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.redis_store import set_redis  # noqa: E402

VISITOR = "test-visitor-0001"
OTHER = "test-visitor-0002"


async def _ensure_database() -> bool:
    dsn = TEST_DB.replace("+asyncpg", "")
    server, name = dsn.rsplit("/", 1)
    try:
        conn = await asyncpg.connect(f"{server}/postgres", timeout=3)
    except (OSError, asyncpg.PostgresError):
        return False
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    return True


@pytest.fixture(scope="session")
async def database():
    if not await _ensure_database():
        pytest.skip("Нет Postgres на порту 5434: запустите docker compose up -d postgres")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
    yield
    await engine.dispose()


@pytest.fixture
def redis():
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    set_redis(client)
    return client


@pytest.fixture
async def client(database, redis):
    """API с уже проиндексированной демо-базой. Свои документы гостей чистятся перед тестом."""
    async with app.router.lifespan_context(app):
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM documents WHERE visitor_id IS NOT NULL"))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Visitor-Id": VISITOR},
        ) as c:
            yield c
