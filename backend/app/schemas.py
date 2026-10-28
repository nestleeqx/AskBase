from datetime import datetime

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
    guest_docs_limit: int
    guest_docs_left: int
    max_upload_mb: float
    max_pdf_pages: int
    max_doc_chars: int
    guest_docs_ttl_hours: int


class DocumentList(BaseModel):
    documents: list[DocumentOut]
    limits: UploadLimits


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


class SearchOut(BaseModel):
    question: str
    took_ms: int
    embedding_model: str
    results: list[SearchHit]
