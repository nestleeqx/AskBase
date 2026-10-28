"""Ответы администратора на вопросы, на которые бот не ответил.

Владелец пишет ответ прямо в разделе «Бот не смог ответить», и все такие ответы собираются
в документ «Ответы администратора». Документ индексируется как обычный TXT — со следующего
вопроса бот находит ответ в нём и ссылается на него как на источник.
"""

import time

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings import EmbeddingProvider
from app.models import Document, KbAnswer
from app.services.extract import Extracted, extract_file
from app.services.indexing import ingest

ANSWERS_FILE = "otvety-administratora.txt"
ANSWERS_TITLE = "Ответы администратора"
MAX_ANSWERS = 30


def not_answers_doc():
    """Условие «это не документ с ответами администратора» — он не считается в лимит гостя."""
    return or_(Document.filename.is_(None), Document.filename != ANSWERS_FILE)


def answers_text(rows: list[KbAnswer]) -> str:
    parts = ["ОТВЕТЫ АДМИНИСТРАТОРА КЛИНИКИ", ""]
    for row in rows:
        parts += [row.question, row.answer, ""]
    return "\n".join(parts)


async def add_answer(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    visitor: str,
    question: str,
    answer: str,
    message_id: int | None,
) -> Document:
    rows = list(
        await session.scalars(
            select(KbAnswer).where(KbAnswer.visitor_id == visitor).order_by(KbAnswer.id)
        )
    )
    if len(rows) >= MAX_ANSWERS:
        raise HTTPException(
            409, f"В демо можно добавить до {MAX_ANSWERS} ответов — удалите документ с ответами."
        )
    row = KbAnswer(visitor_id=visitor, question=question, answer=answer, message_id=message_id)
    session.add(row)
    rows.append(row)

    doc = await session.scalar(
        select(Document).where(Document.visitor_id == visitor, Document.filename == ANSWERS_FILE)
    )
    if doc is None:
        doc = Document(visitor_id=visitor, title=ANSWERS_TITLE, kind="txt", filename=ANSWERS_FILE)
        session.add(doc)
    data = answers_text(rows).encode()
    doc.status, doc.size_bytes = "indexing", len(data)
    await session.commit()

    async def load() -> Extracted:
        return extract_file("txt", data, ANSWERS_FILE, get_settings().max_pdf_pages)

    doc = await ingest(session, embedder, doc, load, time.perf_counter())
    # Заголовок TXT берётся из имени файла — оставляем понятное название
    doc.title = ANSWERS_TITLE
    await session.commit()
    return doc
