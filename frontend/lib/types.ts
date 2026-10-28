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

export type SearchResult = {
  question: string;
  took_ms: number;
  embedding_model: string;
  results: SearchHit[];
};
