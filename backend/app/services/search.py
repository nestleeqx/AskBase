"""Гибридный поиск фрагментов: по смыслу (векторы) и по словам (полнотекстовый индекс).

Векторы находят перефразировки («чистка» ↔ «профессиональная гигиена»), полнотекстовый поиск —
точные слова: фамилии, названия процедур, цифры. Два списка сливаются методом RRF:
у фрагмента тем больше очков, чем выше он в каждом из списков.
"""

import re
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import EmbeddingProvider
from app.models import Chunk, Document
from app.services.redis_store import query_vector

# Сколько кандидатов брать из каждого списка и константа сглаживания RRF
CANDIDATES = 20
RRF_K = 60
_WORD = re.compile(r"[0-9a-zа-яё]+")


@dataclass
class Hit:
    chunk: Chunk
    document: Document
    # Косинусная близость вопроса и фрагмента: 1 — совпадает по смыслу, 0 — не связан
    similarity: float
    vector_rank: int | None
    keyword_rank: int | None
    score: float


def keywords(question: str) -> list[str]:
    words = [w for w in _WORD.findall(question.lower()) if len(w) > 1]
    return list(dict.fromkeys(words))[:20]


def visible_to(visitor: str):
    """Документы клиники видны всем, свои документы гостя — только ему."""
    return and_(
        Document.status == "ready",
        or_(Document.visitor_id.is_(None), Document.visitor_id == visitor),
    )


async def search(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    redis: Redis,
    question: str,
    visitor: str,
    top_k: int,
) -> list[Hit]:
    vector = await query_vector(redis, embedder, question)
    distance = Chunk.embedding.cosine_distance(vector)
    where = and_(visible_to(visitor), Chunk.embedding_model == embedder.model_id)

    by_vector = list(
        await session.scalars(
            select(Chunk.id).join(Document).where(where).order_by(distance).limit(CANDIDATES)
        )
    )

    by_words: list[int] = []
    words = keywords(question)
    if words:
        # «или» между словами: вопрос клиента редко содержит все слова фрагмента
        query = func.to_tsquery("russian", " | ".join(words))
        rank = func.ts_rank_cd(Chunk.tsv, query)
        by_words = list(
            await session.scalars(
                select(Chunk.id)
                .join(Document)
                .where(where, Chunk.tsv.op("@@")(query))
                .order_by(rank.desc(), Chunk.id)
                .limit(CANDIDATES)
            )
        )

    scores: dict[int, float] = {}
    for ranking in (by_vector, by_words):
        for i, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + i + 1)
    top = sorted(scores, key=lambda cid: (-scores[cid], cid))[:top_k]
    if not top:
        return []

    rows = (
        await session.execute(
            select(Chunk, Document, (1 - distance).label("similarity"))
            .join(Document)
            .where(Chunk.id.in_(top))
        )
    ).all()
    found = {chunk.id: (chunk, doc, float(sim)) for chunk, doc, sim in rows}
    vector_pos = {cid: i + 1 for i, cid in enumerate(by_vector)}
    word_pos = {cid: i + 1 for i, cid in enumerate(by_words)}
    return [
        Hit(
            chunk=found[cid][0],
            document=found[cid][1],
            similarity=found[cid][2],
            vector_rank=vector_pos.get(cid),
            keyword_rank=word_pos.get(cid),
            score=scores[cid],
        )
        for cid in top
        if cid in found
    ]
