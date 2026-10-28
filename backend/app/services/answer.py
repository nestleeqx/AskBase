"""Ответ на вопрос клиента по базе знаний.

1. Уточнение с учётом истории: «а сколько стоит?» → «сколько стоят виниры?» (только если
   история есть).
2. Поиск фрагментов (гибридный, топ-6).
3. Ничего близкого не нашлось — сразу передаём администратору, модель не вызываем.
4. Модель отвечает строго по фрагментам и называет, какие использовала. Ответ без
   подтверждённых источников не принимается: такой вопрос тоже уходит администратору.
"""

import logging
import time
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings import EmbeddingError, EmbeddingProvider
from app.llm import LLMError, LLMProvider
from app.services.prompts import (
    ANSWER_SYSTEM,
    CONDENSE_SYSTEM,
    BotAnswer,
    CondensedQuestion,
    answer_prompt,
    condense_prompt,
)
from app.services.redis_store import cached_complete
from app.services.search import Hit, search

log = logging.getLogger(__name__)

HANDOFF = "Уточню у администратора и вернусь с ответом."
UNAVAILABLE = (
    "Не получилось найти ответ прямо сейчас — передал ваш вопрос администратору, "
    "он ответит в ближайшее время."
)

# Почему бот не ответил сам — показывается в админке
REASONS = {
    "answered": "Ответ найден в документах",
    "no_match": "В базе нет ничего похожего — нейросеть не вызывалась",
    "not_in_docs": "Нейросеть не нашла ответа во фрагментах",
    "no_sources": "Нейросеть не подтвердила ответ фрагментами",
    "error": "Сервис ответов был недоступен",
}


@dataclass
class Source:
    id: str
    title: str
    kind: str


@dataclass
class AnswerResult:
    answered: bool
    # Текст для клиента без строки об источнике — её добавляет канал (чат, Telegram)
    text: str
    sources: list[Source]
    topic: str
    query: str
    reason: str
    hits: list[Hit] = field(default_factory=list)
    used_chunk_ids: list[int] = field(default_factory=list)
    search_ms: int = 0
    llm_ms: int = 0
    total_ms: int = 0
    cached: bool = False


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def fragment_title(hit: Hit) -> str:
    heading = hit.chunk.heading
    if heading and heading != hit.document.title:
        return f"{hit.document.title} — {heading}"
    return hit.document.title


async def answer_question(
    session: AsyncSession,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    redis: Redis,
    question: str,
    history: list[tuple[str, str]],
    visitor: str,
) -> AnswerResult:
    """history — последние сообщения диалога: пары (user | bot | operator, текст)."""
    settings = get_settings()
    started = time.perf_counter()
    llm_ms = 0
    cached = True

    try:
        query = question
        if history:
            t = time.perf_counter()
            condensed, hit = await cached_complete(
                redis, llm, CONDENSE_SYSTEM, condense_prompt(history, question), CondensedQuestion
            )
            llm_ms += _ms(t)
            cached &= hit
            query = " ".join(condensed.query.split()) or question

        t = time.perf_counter()
        hits = await search(session, embedder, redis, query, visitor, settings.search_top_k)
        search_ms = _ms(t)

        def handoff(reason: str, topic: str = "other") -> AnswerResult:
            return AnswerResult(
                answered=False,
                text=HANDOFF,
                sources=[],
                topic=topic,
                query=query,
                reason=reason,
                hits=hits,
                search_ms=search_ms,
                llm_ms=llm_ms,
                total_ms=_ms(started),
                cached=cached and llm_ms > 0,
            )

        close = any(h.similarity >= settings.answer_min_similarity for h in hits)
        if not hits or not (close or any(h.keyword_rank for h in hits)):
            return handoff("no_match")

        t = time.perf_counter()
        prompt = answer_prompt(
            [(fragment_title(h), h.chunk.text) for h in hits], history, question, query
        )
        reply, hit = await cached_complete(redis, llm, ANSWER_SYSTEM, prompt, BotAnswer)
        llm_ms += _ms(t)
        cached &= hit
    except (LLMError, EmbeddingError):
        log.exception("Ответ не получен: %s", question)
        return AnswerResult(
            answered=False,
            text=UNAVAILABLE,
            sources=[],
            topic="other",
            query=question,
            reason="error",
            total_ms=_ms(started),
        )

    if not reply.answered or not reply.answer.strip():
        return handoff("not_in_docs", reply.topic)
    used = [hits[i - 1] for i in dict.fromkeys(reply.source_ids) if 1 <= i <= len(hits)]
    if not used:
        return handoff("no_sources", reply.topic)

    sources: dict[str, Source] = {}
    for h in used:
        sources.setdefault(h.document.id, Source(h.document.id, h.document.title, h.document.kind))
    return AnswerResult(
        answered=True,
        text=reply.answer.strip(),
        sources=list(sources.values()),
        topic=reply.topic,
        query=query,
        reason="answered",
        hits=hits,
        used_chunk_ids=[h.chunk.id for h in used],
        search_ms=search_ms,
        llm_ms=llm_ms,
        total_ms=_ms(started),
        cached=cached,
    )


def sources_line(titles: list[str]) -> str:
    """«Источник: Прайс-лист» — строка под ответом бота."""
    if not titles:
        return ""
    label = "Источник" if len(titles) == 1 else "Источники"
    return f"{label}: {', '.join(titles)}"
