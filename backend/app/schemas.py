from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    title: str
    kind: str
    filename: str | None
    source_url: str | None
    status: str
    error: str | None
    chunks_count: int
    chars: int
    pages: int | None
    size_bytes: int
    index_ms: int | None
    created_at: datetime
    # Документ клиники (общий) или свой документ гостя
    own: bool
    # Можно скачать оригинал: хранятся только файлы демо-базы
    downloadable: bool


class UploadLimits(BaseModel):
    # Владелец загружает в общую базу клиники — гостевые лимиты к нему не относятся
    owner: bool = False
    guest_docs_limit: int
    guest_docs_left: int
    max_upload_mb: float
    max_pdf_pages: int
    max_doc_chars: int
    guest_docs_ttl_hours: int


class DocumentList(BaseModel):
    # Страница списка: первые limit документов — остальные админка подгружает прокруткой
    documents: list[DocumentOut]
    limits: UploadLimits
    has_more: bool = False
    # Всего документов и готовых фрагментов в базе — не только на этой странице
    total: int = 0
    chunks_total: int = 0


class UrlIn(BaseModel):
    url: str = Field(min_length=4, max_length=1000)


class ChunkOut(BaseModel):
    id: int
    position: int
    heading: str | None
    text: str


class DocumentChunks(BaseModel):
    document: DocumentOut
    chunks: list[ChunkOut]


class SearchIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class DocumentRef(BaseModel):
    id: str
    title: str
    kind: str
    own: bool


class SearchHit(BaseModel):
    rank: int
    document: DocumentRef
    chunk: ChunkOut
    similarity: float
    # Место во «смысловом» списке и в списке по словам; None — фрагмент туда не попал
    vector_rank: int | None
    keyword_rank: int | None


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Пусто — новый диалог
    conversation_id: str | None = None


class SourceOut(BaseModel):
    id: str
    title: str
    kind: str


class TraceHit(BaseModel):
    rank: int
    document: DocumentRef
    heading: str | None
    text: str
    similarity: float
    # Фрагмент вошёл в ответ
    used: bool


class Trace(BaseModel):
    # По какому вопросу искали: после уточнения с учётом истории он может отличаться
    query: str
    reason: str
    reason_label: str
    hits: list[TraceHit]
    search_ms: int
    llm_ms: int
    cached: bool


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    answered: bool | None = None
    # Служебные сообщения бота: booking — заявка на запись, operator — клиент позвал человека
    reason: str | None = None
    topic: str | None = None
    topic_label: str | None = None
    sources: list[SourceOut] = []
    trace: Trace | None = None
    latency_ms: int | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    # Последние сообщения тестового чата; has_more — есть более ранние
    messages: list[MessageOut]
    has_more: bool = False


class ChatReply(BaseModel):
    conversation_id: str
    user: MessageOut
    bot: MessageOut


class SearchOut(BaseModel):
    question: str
    took_ms: int
    embedding_model: str
    results: list[SearchHit]


class DialogLast(BaseModel):
    role: str
    text: str
    created_at: datetime


class DialogSummary(BaseModel):
    id: str
    # Имя клиента в Telegram и ник
    title: str
    username: str | None
    # Вымышленный демо-диалог: виден всем, ответить в нём нельзя
    demo: bool
    waiting_since: datetime | None
    # Когда клиенту последний раз понадобился человек — по нему админка подаёт сигнал
    attention_at: datetime | None = None
    # Пока не истекло, отвечает администратор, а бот молчит
    operator_until: datetime | None
    updated_at: datetime
    messages_count: int
    last: DialogLast | None


class DialogAttention(BaseModel):
    """Диалог, где клиенту последним понадобился человек, — для сигнала в админке."""

    id: str
    title: str
    attention_at: datetime


class DialogList(BaseModel):
    # Страница списка; has_more — есть ещё диалоги, админка подгрузит их прокруткой
    dialogs: list[DialogSummary]
    has_more: bool = False
    # Сколько диалогов ждут ответа администратора — бейдж в меню
    waiting: int
    # Последний зов человека по всем диалогам, а не только на этой странице
    latest_attention: DialogAttention | None = None


class BookingOut(BaseModel):
    id: str
    conversation_id: str
    client: str
    name: str
    phone: str
    reason: str | None
    preferred_time: str
    status: str
    created_at: datetime
    # Последнее действие клиента с заявкой в боте: создал, изменил, отменил
    client_changed_at: datetime
    demo: bool


class DialogDetail(DialogSummary):
    # Страница переписки: последние сообщения или те, что раньше параметра before
    messages: list[MessageOut]
    # Есть сообщения раньше этой страницы — админка подгрузит их при прокрутке вверх
    has_more: bool = False
    bookings: list[BookingOut]


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class BookingList(BaseModel):
    # Страница списка с выбранным статусом; has_more — есть ещё заявки
    bookings: list[BookingOut]
    has_more: bool = False
    # Ждут звонка — бейдж в меню
    new: int
    # Сколько заявок в каждом статусе и всего (all) — для вкладок-фильтров
    counts: dict[str, int] = {}
    # Последнее действие клиента по всем заявкам — для сигнала в админке
    latest_client_change: BookingOut | None = None


class BookingPatch(BaseModel):
    status: Literal["new", "confirmed", "cancelled"]


class TelegramStatus(BaseModel):
    enabled: bool
    username: str | None = None
    # Посетитель привязал свой Telegram-чат и видит в «Диалогах» свою переписку
    linked: bool = False
    # Уведомления менеджеру настроены (MANAGER_CHAT_ID)
    manager: bool = False


class TelegramLink(BaseModel):
    url: str
