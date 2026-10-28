"""Диалоги: история для бота и сохранение вопросов и ответов."""

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings import EmbeddingProvider
from app.llm import LLMProvider
from app.models import Conversation, Message, now
from app.services.answer import REASONS, AnswerResult, answer_question


async def recent_history(session: AsyncSession, conversation_id: str) -> list[tuple[str, str]]:
    """Последние сообщения диалога по порядку — бот понимает уточнения вроде «а сколько стоит?»."""
    limit = get_settings().history_messages
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return [(m.role, m.text) for m in reversed(list(rows))]


def trace_of(result: AnswerResult) -> dict:
    used = set(result.used_chunk_ids)
    return {
        "query": result.query,
        "reason": result.reason,
        "reason_label": REASONS[result.reason],
        "hits": [
            {
                "rank": i + 1,
                "document": {
                    "id": h.document.id,
                    "title": h.document.title,
                    "kind": h.document.kind,
                    "own": h.document.visitor_id is not None,
                },
                "heading": h.chunk.heading,
                "text": h.chunk.text,
                "similarity": round(h.similarity, 4),
                "used": h.chunk.id in used,
            }
            for i, h in enumerate(result.hits)
        ],
        "search_ms": result.search_ms,
        "llm_ms": result.llm_ms,
        "cached": result.cached,
    }


async def ask(
    session: AsyncSession,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    redis: Redis,
    conversation: Conversation,
    question: str,
    visitor: str,
    use_history: bool = True,
) -> tuple[Message, Message, AnswerResult]:
    """Вопрос клиента → ответ бота; оба сообщения сохраняются в диалоге.

    use_history=False — вопрос самостоятельный (кнопка в Telegram): без истории ответ
    одинаковый для всех и берётся из кеша.
    """
    history = await recent_history(session, conversation.id) if use_history else []
    result = await answer_question(session, llm, embedder, redis, question, history, visitor)

    user = Message(conversation_id=conversation.id, role="user", text=question)
    bot = Message(
        conversation_id=conversation.id,
        role="bot",
        text=result.text,
        answered=result.answered,
        reason=result.reason,
        topic=result.topic,
        sources=[{"id": s.id, "title": s.title, "kind": s.kind} for s in result.sources],
        trace=trace_of(result),
        latency_ms=result.total_ms,
    )
    session.add_all([user, bot])
    conversation.updated_at = now()
    await session.commit()
    return user, bot, result
