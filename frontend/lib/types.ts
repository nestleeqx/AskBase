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
