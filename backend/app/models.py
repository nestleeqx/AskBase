from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now() -> datetime:
    return datetime.now(UTC)


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
