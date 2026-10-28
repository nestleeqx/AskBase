import time

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.deps import EmbedderDep, IpDep, RedisDep, SessionDep, VisitorDep
from app.schemas import ChunkOut, DocumentRef, SearchHit, SearchIn, SearchOut
from app.services.redis_store import hit_limit
from app.services.search import search

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchOut)
async def search_chunks(
    body: SearchIn,
    session: SessionDep,
    redis: RedisDep,
    embedder: EmbedderDep,
    ip: IpDep,
    visitor: VisitorDep,
):
    """Какие фрагменты базы нашлись по вопросу — то же, что увидит нейросеть перед ответом."""
    s = get_settings()
    question = " ".join(body.question.split())
    if not question:
        raise HTTPException(422, "Введите вопрос.")
    if len(question) > s.max_question_chars:
        raise HTTPException(422, f"Вопрос длиннее {s.max_question_chars} символов — сократите его.")
    await hit_limit(redis, "search", ip, s.searches_per_hour)

    started = time.perf_counter()
    hits = await search(session, embedder, redis, question, visitor, s.search_top_k)
    return SearchOut(
        question=question,
        took_ms=round((time.perf_counter() - started) * 1000),
        embedding_model=embedder.model_id,
        results=[
            SearchHit(
                rank=i + 1,
                document=DocumentRef(
                    id=h.document.id,
                    title=h.document.title,
                    kind=h.document.kind,
                    own=h.document.visitor_id == visitor,
                ),
                chunk=ChunkOut(
                    id=h.chunk.id,
                    position=h.chunk.position,
                    heading=h.chunk.heading,
                    text=h.chunk.text,
                ),
                similarity=round(h.similarity, 4),
                vector_rank=h.vector_rank,
                keyword_rank=h.keyword_rank,
            )
            for i, h in enumerate(hits)
        ],
    )
