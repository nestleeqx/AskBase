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
  guest_docs_limit: number;
  guest_docs_left: number;
  max_upload_mb: number;
  max_pdf_pages: number;
  max_doc_chars: number;
  guest_docs_ttl_hours: number;
};

export type DocumentList = { documents: Doc[]; limits: UploadLimits };

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

export type Conversation = { id: string; messages: ChatMessage[] };
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
  demo: boolean;
};

export type DialogList = { dialogs: DialogSummary[]; waiting: number };
export type DialogDetail = DialogSummary & { messages: ChatMessage[]; bookings: Booking[] };
export type BookingList = { bookings: Booking[]; new: number };

export type TelegramStatus = {
  enabled: boolean;
  username: string | null;
  /** Свой Telegram-чат привязан: его переписка видна в «Диалогах» */
  linked: boolean;
  /** Уведомления менеджеру настроены */
  manager: boolean;
};
