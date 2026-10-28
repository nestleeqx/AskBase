"""Индексация: текст документа → фрагменты → эмбеддинги → таблица chunks."""

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings import EmbeddingError, EmbeddingProvider
from app.models import Chunk, Document, KbAnswer, now
from app.services.chunking import Draft, embedding_input, make_chunks
from app.services.extract import Extracted, ExtractError

log = logging.getLogger(__name__)

EMBEDDING_FAILED = (
    "Сервис поиска временно недоступен — документ не проиндексирован. Попробуйте позже."
)


async def _save_chunks(
    session: AsyncSession, embedder: EmbeddingProvider, doc: Document, drafts: list[Draft]
) -> None:
    vectors = await embedder.embed_documents([embedding_input(doc.title, d) for d in drafts])
    await session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    session.add_all(
        Chunk(
            document_id=doc.id,
            position=i,
            heading=(d.heading or "")[:300] or None,
            text=d.text,
            embedding=vector,
            embedding_model=embedder.model_id,
        )
        for i, (d, vector) in enumerate(zip(drafts, vectors, strict=True))
    )
    doc.chunks_count = len(drafts)


async def ingest(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    doc: Document,
    load: Callable[[], Awaitable[Extracted]],
    started: float,
) -> Document:
    """Читает документ, режет и индексирует. Документ уже сохранён со статусом «индексируется»;
    ошибка чтения или API не роняет запрос, а остаётся в статусе документа."""
    settings = get_settings()
    try:
        extracted = await load()
        if extracted.chars > settings.max_doc_chars:
            raise ExtractError(
                f"В документе больше {settings.max_doc_chars:,} символов — для демо это "
                "слишком много.".replace(",", " ")
            )
        drafts = make_chunks(extracted.units)
        if not drafts:
            raise ExtractError("В документе не нашлось текста.")
        if not doc.seed_key and extracted.title:
            doc.title = extracted.title[:200]
        doc.chars, doc.pages = extracted.chars, extracted.pages
        await _save_chunks(session, embedder, doc, drafts)
        doc.status, doc.error = "ready", None
        doc.indexed_at = now()
    except ExtractError as e:
        doc.status, doc.error = "error", str(e)
    except EmbeddingError:
        log.exception("Эмбеддинги: документ %s не проиндексирован", doc.id)
        doc.status, doc.error = "error", EMBEDDING_FAILED
    doc.index_ms = round((time.perf_counter() - started) * 1000)
    await session.commit()
    return doc


async def reembed(session: AsyncSession, embedder: EmbeddingProvider, doc: Document) -> None:
    """Пересчитать векторы сохранённых фрагментов другой моделью — текст не перечитывается."""
    chunks = list(await session.scalars(select(Chunk).where(Chunk.document_id == doc.id)))
    drafts = [Draft(c.heading, c.text) for c in sorted(chunks, key=lambda c: c.position)]
    await _save_chunks(session, embedder, doc, drafts)
    await session.commit()


async def cleanup_guest_docs(session: AsyncSession, ttl_hours: int) -> int:
    """Свои документы гостей живут сутки: демо не копит чужие файлы."""
    border = now() - timedelta(hours=ttl_hours)
    result = await session.execute(
        delete(Document).where(Document.visitor_id.is_not(None), Document.created_at < border)
    )
    await session.execute(delete(KbAnswer).where(KbAnswer.created_at < border))
    await session.commit()
    return result.rowcount or 0
