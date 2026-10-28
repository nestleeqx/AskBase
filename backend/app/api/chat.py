from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.deps import EmbedderDep, IpDep, LLMDep, RedisDep, SessionDep, VisitorDep
from app.models import Conversation, Message
from app.schemas import ChatIn, ChatReply, ConversationOut, MessageOut
from app.services.dialogs import ask
from app.services.prompts import TOPICS
from app.services.redis_store import hit_limit

router = APIRouter(prefix="/api/chat", tags=["chat"])

NOT_FOUND = "Диалог не найден — начните новый."


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,
        text=m.text,
        answered=m.answered,
        reason=m.reason if m.reason in {"booking", "operator"} else None,
        topic=m.topic,
        topic_label=TOPICS.get(m.topic or ""),
        sources=m.sources or [],
        trace=m.trace,
        latency_ms=m.latency_ms,
        created_at=m.created_at,
    )


async def _own(session: SessionDep, conversation_id: str, visitor: str) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.channel != "test" or conv.visitor_id != visitor:
        raise HTTPException(404, NOT_FOUND)
    return conv


@router.post("", response_model=ChatReply)
async def chat(
    body: ChatIn,
    session: SessionDep,
    redis: RedisDep,
    llm: LLMDep,
    embedder: EmbedderDep,
    ip: IpDep,
    visitor: VisitorDep,
):
    """Тестовый чат в админке: тот же бот, что в Telegram, с разбором каждого ответа."""
    s = get_settings()
    question = " ".join(body.question.split())
    if not question:
        raise HTTPException(422, "Напишите вопрос.")
    if len(question) > s.max_question_chars:
        raise HTTPException(422, f"Вопрос длиннее {s.max_question_chars} символов — сократите его.")

    if body.conversation_id:
        conv = await _own(session, body.conversation_id, visitor)
    else:
        conv = Conversation(visitor_id=visitor, channel="test")
        session.add(conv)
        await session.flush()
    await hit_limit(redis, "chat", ip, s.questions_per_hour)

    user, bot, _ = await ask(session, llm, embedder, redis, conv, question, visitor)
    return ChatReply(conversation_id=conv.id, user=message_out(user), bot=message_out(bot))


@router.get("/{conversation_id}", response_model=ConversationOut)
async def conversation(conversation_id: str, session: SessionDep, visitor: VisitorDep):
    conv = await _own(session, conversation_id, visitor)
    rows = await session.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
    )
    return ConversationOut(id=conv.id, messages=[message_out(m) for m in rows])
