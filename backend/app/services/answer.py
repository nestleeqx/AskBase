"""Ответ на вопрос клиента по базе знаний.

1. Уточнение с учётом истории: «а сколько стоит?» → «сколько стоят виниры?» (только если
   история есть).
2. Поиск фрагментов (гибридный, топ-6).
3. Ничего близкого не нашлось — сразу передаём администратору, модель не вызываем.
4. Модель отвечает строго по фрагментам и называет, какие использовала. Ответ без
   подтверждённых источников не принимается: такой вопрос тоже уходит администратору.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings import EmbeddingError, EmbeddingProvider
from app.llm import LLMError, LLMProvider
from app.services.prompts import (
    CONDENSE_SYSTEM,
    BotAnswer,
    CondensedQuestion,
    answer_prompt,
    answer_system,
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
    "booking_intent": "Клиент хочет записаться — бот начал запись по шагам",
    "operator_intent": "Клиент попросил администратора",
    "smalltalk": "Приветствие или реплика без вопроса — бот ответил сам",
    "my_booking": "Клиент спросил о своей записи — бот ответил по заявкам",
    "cancel_booking": "Клиент попросил отменить запись",
}
# Тексты для тестового чата: в Telegram вместо них запускается запись по шагам
# или передача администратору
OPERATOR_INTENT = "Передал ваш запрос администратору — он ответит в ближайшее время."
MY_BOOKING_HINT = (
    "Статус своей записи бот покажет в Telegram — там он видит ваши заявки. "
    "В тестовом чате записи нет."
)
CANCEL_BOOKING_HINT = (
    "Отменить запись можно в Telegram-боте клиники — командой /cancel или словами "
    "«отмените запись»."
)


@dataclass
class Source:
    id: str
    title: str
    kind: str


# Реплики без вопроса: (вид, слова, ответ). Порядок важен: «всего доброго» — прощание,
# а не приветствие, «хорошо, спасибо» — благодарность
SMALLTALK = [
    (
        "greeting",
        {
            "привет",
            "приветствую",
            "здравствуйте",
            "здравствуй",
            "здрасте",
            "добрый",
            "доброе",
            "день",
            "вечер",
            "утро",
            "hi",
            "hello",
            "хай",
            "салют",
            "алло",
        },
        "Здравствуйте! Чем могу помочь? Спросите о ценах, врачах, подготовке к процедурам "
        "или записи.",
    ),
    (
        "thanks",
        {"спасибо", "благодарю", "спс", "спасибки"},
        "Пожалуйста! Если появятся вопросы — пишите.",
    ),
    ("bye", {"пока", "свидания", "всего"}, "Всего доброго! Будем рады видеть вас в клинике."),
    (
        "test",
        {"тест", "test", "проверка"},
        "Я на связи! Задайте вопрос о клинике — отвечу по документам.",
    ),
    (
        "ok",
        {
            "ок",
            "окей",
            "ok",
            "хорошо",
            "понятно",
            "ясно",
            "ладно",
            "угу",
            "ага",
            "понял",
            "поняла",
            "отлично",
            "супер",
        },
        "Хорошо! Если появятся вопросы — пишите.",
    ),
]
# Слова, которые не меняют смысла реплики: «спасибо большое», «привет, бот»
_FILLER = {
    "а",
    "ну",
    "и",
    "вам",
    "всем",
    "вас",
    "большое",
    "огромное",
    "бот",
    "еще",
    "до",
    "связи",
    "доброго",
    "дня",
}
_SMALLTALK_WORDS = set().union(*(words for _, words, _ in SMALLTALK)) | _FILLER
_PRIORITY = ["thanks", "bye", "greeting", "test", "ok"]


def smalltalk_reply(text: str) -> str | None:
    """Ответ на «привет», «спасибо», «ок», «тест» — или None, если в сообщении есть вопрос."""
    words = re.findall(r"[a-zа-я]+", text.lower().replace("ё", "е"))
    if not words or len(words) > 5 or any(w not in _SMALLTALK_WORDS for w in words):
        return None
    replies = {kind: (vocab, reply) for kind, vocab, reply in SMALLTALK}
    for kind in _PRIORITY:
        vocab, reply = replies[kind]
        if any(w in vocab for w in words):
            return reply
    return None


def booking_hint(phone: str | None = None) -> str:
    return (
        "Чтобы записаться, нажмите «📅 Записаться» в Telegram-боте клиники — он спросит имя, "
        f"телефон и удобное время. Или позвоните: {phone or get_settings().clinic_phone}."
    )


@dataclass
class AnswerResult:
    # None — клиент не спрашивал, а хотел записаться
    answered: bool | None
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
    # question, booking или operator — чего хочет клиент
    intent: str = "question"
    # Что клиент уже сообщил для записи: name, phone, reason, preferred_time
    draft: dict[str, str] = field(default_factory=dict)


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
    tone: str = "neutral",
) -> AnswerResult:
    """history — последние сообщения диалога: пары (user | bot | operator, текст).
    tone — тон ответов из настроек бота (TONES)."""
    settings = get_settings()
    started = time.perf_counter()
    llm_ms = 0
    cached = True

    # «Привет», «спасибо», «тест» — не вопрос: отвечаем сразу, без поиска и нейросети.
    # Иначе бот передал бы «привет» администратору, а с историей принял бы за продолжение записи
    canned = smalltalk_reply(question)
    if canned:
        return AnswerResult(
            answered=None,
            text=canned,
            sources=[],
            topic="other",
            query=question,
            reason="smalltalk",
            total_ms=_ms(started),
            intent="smalltalk",
        )

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
        reply, hit = await cached_complete(redis, llm, answer_system(tone), prompt, BotAnswer)
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

    if reply.intent == "smalltalk":
        result = handoff("smalltalk", "other")
        result.intent, result.answered = "smalltalk", None
        result.text = reply.answer.strip() or SMALLTALK[0][2]
        return result
    if reply.intent in ("my_booking", "cancel_booking"):
        # Про свою запись клиента знает система, а не документы: отвечает канал (Telegram),
        # в тестовом чате — подсказка
        result = handoff(reply.intent, "booking")
        result.intent, result.answered = reply.intent, None
        result.text = MY_BOOKING_HINT if reply.intent == "my_booking" else CANCEL_BOOKING_HINT
        return result
    if reply.intent != "question":
        booking = reply.intent == "booking"
        result = handoff("booking_intent" if booking else "operator_intent", reply.topic)
        result.intent = reply.intent
        result.answered = None if booking else False
        result.text = booking_hint() if booking else OPERATOR_INTENT
        result.draft = reply.booking.model_dump() if booking else {}
        result.cached = cached
        return result
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
