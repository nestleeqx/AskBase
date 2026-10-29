export type DocKind = "pdf" | "docx" | "txt" | "url";
export type DocStatus = "indexing" | "ready" | "error";

export type Doc = {
  id: string;
  title: string;
  kind: DocKind;
  filename: string | null;
  source_url: string | null;
  status: DocStatus;
  error: string | null;
  chunks_count: number;
  chars: number;
  pages: number | null;
  size_bytes: number;
  index_ms: number | null;
  created_at: string;
  /** Свой документ гостя (виден только ему) или документ клиники */
  own: boolean;
  /** Оригинал можно скачать — хранятся только файлы демо-базы */
  downloadable: boolean;
};

export type UploadLimits = {
  /** Вошёл владелец: документы идут в общую базу клиники, без гостевых лимитов */
  owner: boolean;
  guest_docs_limit: number;
  guest_docs_left: number;
  max_upload_mb: number;
  max_pdf_pages: number;
  max_doc_chars: number;
  guest_docs_ttl_hours: number;
};

/** Страница документов; total и chunks_total — по всей базе, has_more — есть ещё */
export type DocumentList = {
  documents: Doc[];
  limits: UploadLimits;
  has_more: boolean;
  total: number;
  chunks_total: number;
};

export type Chunk = {
  id: number;
  position: number;
  heading: string | null;
  text: string;
};

export type DocumentChunks = { document: Doc; chunks: Chunk[] };

export type SearchHit = {
  rank: number;
  document: { id: string; title: string; kind: DocKind; own: boolean };
  chunk: Chunk;
  similarity: number;
  vector_rank: number | null;
  keyword_rank: number | null;
};

export type Source = { id: string; title: string; kind: DocKind };

export type TraceHit = {
  rank: number;
  document: { id: string; title: string; kind: DocKind; own: boolean };
  heading: string | null;
  text: string;
  similarity: number;
  /** Фрагмент вошёл в ответ */
  used: boolean;
};

export type Trace = {
  query: string;
  reason: "answered" | "no_match" | "not_in_docs" | "no_sources" | "error";
  reason_label: string;
  hits: TraceHit[];
  search_ms: number;
  llm_ms: number;
  cached: boolean;
};

export type ChatMessage = {
  id: number;
  role: "user" | "bot" | "operator";
  text: string;
  answered: boolean | null;
  /** Служебные сообщения бота: booking — заявка на запись, operator — клиент позвал администратора */
  reason: "booking" | "operator" | null;
  topic: string | null;
  topic_label: string | null;
  sources: Source[];
  trace: Trace | null;
  latency_ms: number | null;
  created_at: string;
};

export type Conversation = { id: string; messages: ChatMessage[]; has_more: boolean };
export type ChatReply = { conversation_id: string; user: ChatMessage; bot: ChatMessage };

export type SearchResult = {
  question: string;
  took_ms: number;
  embedding_model: string;
  results: SearchHit[];
};

export type DialogLast = { role: ChatMessage["role"]; text: string; created_at: string };

export type DialogSummary = {
  id: string;
  /** Имя клиента в Telegram */
  title: string;
  username: string | null;
  /** Вымышленный демо-диалог: виден всем, ответить в нём нельзя */
  demo: boolean;
  /** С какого момента клиент ждёт человека */
  waiting_since: string | null;
  /** Когда клиенту последний раз понадобился человек — по этому времени админка подаёт сигнал */
  attention_at: string | null;
  /** До какого времени отвечает администратор, а бот молчит */
  operator_until: string | null;
  updated_at: string;
  messages_count: number;
  last: DialogLast | null;
};

export type BookingStatus = "new" | "confirmed" | "cancelled";

export type Booking = {
  id: string;
  conversation_id: string;
  client: string;
  name: string;
  phone: string;
  reason: string | null;
  preferred_time: string;
  status: BookingStatus;
  created_at: string;
  /** Последнее действие клиента в боте: создал, изменил или отменил заявку. Администратор его не меняет */
  client_changed_at: string;
  demo: boolean;
};

/** Диалог, где клиенту последним понадобился человек, — для сигнала в админке */
export type DialogAttention = { id: string; title: string; attention_at: string };
export type DialogList = {
  dialogs: DialogSummary[];
  has_more: boolean;
  waiting: number;
  latest_attention: DialogAttention | null;
};
/** messages — последние сообщения переписки; has_more — есть более ранние, их подгружают прокруткой вверх */
export type DialogDetail = DialogSummary & { messages: ChatMessage[]; has_more: boolean; bookings: Booking[] };
/** counts — по статусам и всего (all) по всем заявкам; latest_client_change — последнее действие клиента */
export type BookingList = {
  bookings: Booking[];
  has_more: boolean;
  new: number;
  counts: Partial<Record<BookingStatus | "all", number>>;
  latest_client_change: Booking | null;
};

export type TelegramStatus = {
  enabled: boolean;
  username: string | null;
  /** Свой Telegram-чат привязан: его переписка видна в «Диалогах» */
  linked: boolean;
  /** Уведомления менеджеру настроены */
  manager: boolean;
};

export type UnansweredItem = {
  id: number;
  question: string;
  reason: string;
  reason_label: string;
  channel: "telegram" | "test";
  conversation_id: string;
  client: string;
  created_at: string;
  demo: boolean;
  resolved: boolean;
  /** Ответ администратора, добавленный в базу знаний */
  kb_answer: string | null;
};

export type UnansweredList = { items: UnansweredItem[]; has_more: boolean; open: number; resolved: number };

export type Tone = "neutral" | "friendly" | "formal" | "brief";

export type BotSettingsValues = { greeting: string; tone: Tone; phone: string; hours: string };

export type BotSettings = BotSettingsValues & {
  /** Настройки изменены: у гостя — свои, у владельца — общие настройки клиники */
  custom: boolean;
  /** guest — действуют только у гостя, clinic — для всех клиентов */
  scope: "guest" | "clinic";
  defaults: BotSettingsValues;
  tones: Record<Tone, string>;
};

export type AnalyticsDay = { date: string; dialogs: number; questions: number; answered: number };

export type Analytics = {
  days: AnalyticsDay[];
  dialogs: number;
  questions: number;
  answered: number;
  /** Доля вопросов, на которые бот ответил сам: 0..1 */
  answered_share: number | null;
  median_ms: number | null;
  bookings: number;
  operator_requests: number;
  unanswered: number;
  topics: { topic: string; label: string; count: number }[];
  timezone: string;
};

export type AuthStatus = {
  owner: boolean;
  /** Пароль владельца задан на сервере — вход владельца доступен */
  owner_enabled: boolean;
};
