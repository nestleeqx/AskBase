"""Демо-база клиники «Белая линия»: документы из app/seed/docs индексируются при старте.

Повторно документ индексируется, только если поменялся файл или модель эмбеддингов.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.embeddings import EmbeddingError, EmbeddingProvider
from app.models import Chunk, Document
from app.services.extract import Extracted, extract_file
from app.services.indexing import ingest, reembed
from app.services.redis_store import PREFIX

log = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parents[1] / "seed" / "docs"
# Версия разбора и нарезки: увеличьте, если они поменялись, — демо-база переиндексируется
# при следующем запуске, хотя сами файлы те же
INDEX_VERSION = 2


@dataclass(frozen=True)
class SeedDoc:
    key: str
    title: str
    file: str
    kind: str
    # Страница на сайте клиники (фронтенд), с которой «загружен» документ
    site_path: str | None = None

    @property
    def path(self) -> Path:
        return SEED_DIR / self.file


SEED_DOCS = [
    SeedDoc("prajs", "Прайс-лист", "prajs-list.pdf", "pdf"),
    SeedDoc("vrachi", "Врачи и график работы", "vrachi-i-grafik.docx", "docx"),
    SeedDoc("faq", "Частые вопросы пациентов", "faq.txt", "txt"),
    SeedDoc(
        "pravila",
        "Правила записи на приём",
        "pravila-zapisi.html",
        "url",
        site_path="/clinic/pravila-zapisi.html",
    ),
]
SEED_BY_KEY = {s.key: s for s in SEED_DOCS}


def _source_url(seed: SeedDoc) -> str | None:
    return f"{get_settings().public_site_url}{seed.site_path}" if seed.site_path else None


async def ensure_seed(
    sessions: async_sessionmaker, embedder: EmbeddingProvider, redis: Redis
) -> None:
    lock = f"{PREFIX}seed-lock"
    # Несколько процессов стартуют одновременно (serverless) — индексирует один
    if not await redis.set(lock, "1", nx=True, ex=120):
        return
    try:
        for seed in SEED_DOCS:
            await _ensure_one(sessions, embedder, seed)
        await _reembed_stale(sessions, embedder)
    except EmbeddingError:
        log.exception("Демо-база не проиндексирована: API эмбеддингов недоступен")
    finally:
        await redis.delete(lock)


async def _ensure_one(sessions: async_sessionmaker, embedder: EmbeddingProvider, seed: SeedDoc):
    data = seed.path.read_bytes()
    digest = hashlib.sha256(f"{INDEX_VERSION}\x00".encode() + data).hexdigest()
    async with sessions() as session:
        doc = await session.scalar(select(Document).where(Document.seed_key == seed.key))
        if doc and doc.status == "ready" and doc.content_hash == digest:
            return
        started = time.perf_counter()
        if doc is None:
            doc = Document(seed_key=seed.key, kind=seed.kind, title=seed.title)
            session.add(doc)
        doc.title, doc.kind = seed.title, seed.kind
        doc.filename = None if seed.site_path else seed.file
        doc.source_url = _source_url(seed)
        doc.size_bytes, doc.content_hash, doc.status = len(data), digest, "indexing"
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return

        async def load() -> Extracted:
            kind = "html" if seed.kind == "url" else seed.kind
            return extract_file(kind, data, seed.file, max_pages=100)

        await ingest(session, embedder, doc, load, started)
        log.info("Демо-документ «%s»: %s, фрагментов %d", seed.title, doc.status, doc.chunks_count)


async def _reembed_stale(sessions: async_sessionmaker, embedder: EmbeddingProvider) -> None:
    """После смены провайдера эмбеддингов пересчитать векторы уже загруженных документов."""
    async with sessions() as session:
        stale = await session.scalars(
            select(Document)
            .join(Chunk)
            .where(Chunk.embedding_model != embedder.model_id)
            .group_by(Document.id)
            .having(func.count(Chunk.id) > 0)
        )
        for doc in list(stale):
            await reembed(session, embedder, doc)
            log.info("Пересчитаны векторы «%s» для %s", doc.title, embedder.model_id)
