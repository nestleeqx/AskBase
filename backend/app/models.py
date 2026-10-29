from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now() -> datetime:
    return datetime.now(UTC)


# Настройки бота для всех клиентов (их меняет владелец клиники)
CLINIC_OWNER = "clinic"

# Владелец вымышленных демо-диалогов: их видят все посетители, но менять не может никто.
# Настоящие id посетителей длиннее, поэтому совпасть с ним не могут
DEMO_VISITOR = "demo"


class Document(Base):
    """Документ базы знаний. visitor_id пуст у документов клиники, общих для всех;
    у своих документов гостя — его id: их видит только он."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    visitor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Ключ демо-документа из app/seed (prajs, vrachi, faq, pravila)
    seed_key: Mapped[str | None] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    # pdf, docx, txt или url
    kind: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int | None] = mapped_column(Integer)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    # sha256 исходника: демо-документ переиндексируется, если файл в репозитории поменялся
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # indexing → ready | error
    status: Mapped[str] = mapped_column(String(12), default="indexing")
    error: Mapped[str | None] = mapped_column(Text)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    # Сколько заняла индексация: от загрузки до готовности к поиску
    index_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class Chunk(Base):
    """Фрагмент документа: текст, вектор смысла и полнотекстовый индекс."""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    # Раздел документа, к которому относится начало фрагмента
    heading: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    # Размерность у провайдеров разная, поэтому колонка без фиксированной размерности.
    # Фрагментов в базе сотни — точный поиск без индекса укладывается в миллисекунды
    embedding: Mapped[list[float]] = mapped_column(Vector())
    # Какой моделью посчитан вектор: при смене провайдера фрагменты пересчитываются
    embedding_model: Mapped[str] = mapped_column(String(80), index=True)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', coalesce(heading, '') || ' ' || text)", persisted=True),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base):
    """Диалог с ботом: тестовый чат в админке или переписка в Telegram."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # Чей это диалог в демо: тестовый чат видит только тот, кто его начал; Telegram-чат —
    # тот, кто привязал его через «Открыть бота». DEMO_VISITOR — вымышленные диалоги для всех
    visitor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # test — тестовый чат в админке, telegram — переписка с ботом
    channel: Mapped[str] = mapped_column(String(16), default="test")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # С какого момента клиент ждёт человека: бот не нашёл ответа или клиент позвал
    # администратора. Сбрасывается ответом администратора
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Последний раз, когда клиенту понадобился человек: позвал администратора, бот не нашёл
    # ответа, клиент написал, пока отвечает администратор. Служебные сообщения о записи его
    # не меняют — по нему админка сигналит «клиент ждёт администратора»
    attention_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # До какого времени отвечает администратор, а бот молчит. Продлевается каждым ответом
    operator_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # user — клиент, bot — ответ бота, operator — ответ администратора
    role: Mapped[str] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(Text)
    # У ответов бота: нашёлся ли ответ в документах. False — вопрос передан администратору
    answered: Mapped[bool | None] = mapped_column(Boolean)
    # Почему бот ответил так: answered, no_match, … (см. REASONS), а также служебные
    # booking — заявка на запись, operator — клиент попросил администратора
    reason: Mapped[str | None] = mapped_column(String(20))
    topic: Mapped[str | None] = mapped_column(String(20))
    # Документы-источники: [{"id", "title", "kind"}]
    sources: Mapped[list | None] = mapped_column(JSON)
    # Что искал бот и что нашёл — для разбора ответа в админке
    trace: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Вопрос без ответа разобран: владелец добавил ответ в базу или отметил вручную
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class TelegramChat(Base):
    """Чат клиента с ботом в Telegram — у каждого один диалог."""

    __tablename__ = "telegram_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True
    )
    # Имя клиента в Telegram и ник — чтобы администратор понимал, с кем говорит
    title: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Booking(Base):
    """Заявка на запись, собранная ботом по шагам. Время подтверждает администратор."""

    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(32))
    # Что беспокоит или на какую услугу — клиент может пропустить
    reason: Mapped[str | None] = mapped_column(String(300))
    preferred_time: Mapped[str] = mapped_column(String(200))
    # new — ждёт звонка администратора, confirmed — подтверждена, cancelled — отменена
    status: Mapped[str] = mapped_column(String(12), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Когда клиент последний раз создал, изменил или отменил заявку в боте. Действия
    # администратора (подтвердил, отменил) его не меняют — по нему админка сигналит о новом
    client_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now)


class BotProfile(Base):
    """Настройки бота: приветствие, тон, контакты. owner — CLINIC_OWNER для всех клиентов
    или id посетителя демо: его настройки действуют в его тестовом чате и Telegram-чате."""

    __tablename__ = "bot_profiles"

    owner: Mapped[str] = mapped_column(String(64), primary_key=True)
    greeting: Mapped[str] = mapped_column(Text)
    # neutral, friendly, formal, brief — см. TONES в prompts
    tone: Mapped[str] = mapped_column(String(12))
    phone: Mapped[str] = mapped_column(String(40))
    hours: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KbAnswer(Base):
    """Ответ администратора на вопрос, на который бот не ответил. Все ответы посетителя
    собираются в документ «Ответы администратора» — бот находит их, как любой документ."""

    __tablename__ = "kb_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # Ответ бота «не нашёл», на который отвечает администратор
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
