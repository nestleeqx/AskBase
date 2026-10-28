import time

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, or_, select

from app.config import get_settings
from app.deps import EmbedderDep, IpDep, RedisDep, SessionDep, Viewer, ViewerDep
from app.models import CLINIC_OWNER, Chunk, Document, KbAnswer
from app.schemas import ChunkOut, DocumentChunks, DocumentList, DocumentOut, UploadLimits, UrlIn
from app.services.extract import Extracted, ExtractError, extract_file, kind_of
from app.services.fetch import fetch_page
from app.services.indexing import ingest
from app.services.kb_answers import ANSWERS_FILE, not_answers_doc
from app.services.redis_store import hit_limit
from app.services.seed import SEED_BY_KEY

router = APIRouter(prefix="/api/documents", tags=["documents"])

NOT_FOUND = "Документ не найден — возможно, его уже удалили."
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
}


def _owns(viewer: Viewer, doc: Document) -> bool:
    """Документ можно удалить: у гостя — свои, у владельца — загруженные в базу клиники.
    Документы демо-базы (seed) не удаляет никто: их видят все гости."""
    if viewer.owner:
        return doc.visitor_id is None and not doc.seed_key
    return doc.visitor_id == viewer.visitor


def to_out(doc: Document, viewer: Viewer) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        kind=doc.kind,
        filename=doc.filename,
        source_url=doc.source_url,
        status=doc.status,
        error=doc.error,
        chunks_count=doc.chunks_count,
        chars=doc.chars,
        pages=doc.pages,
        size_bytes=doc.size_bytes,
        index_ms=doc.index_ms,
        created_at=doc.created_at,
        own=_owns(viewer, doc),
        downloadable=bool(doc.seed_key) and doc.kind != "url",
    )


async def _own_count(session: SessionDep, visitor: str) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.visitor_id == visitor, not_answers_doc())
    )


async def _limits(session: SessionDep, viewer: Viewer) -> UploadLimits:
    s = get_settings()
    return UploadLimits(
        owner=viewer.owner,
        guest_docs_limit=s.guest_docs_limit,
        guest_docs_left=max(0, s.guest_docs_limit - await _own_count(session, viewer.visitor)),
        max_upload_mb=s.max_upload_mb,
        max_pdf_pages=s.max_pdf_pages,
        max_doc_chars=s.max_doc_chars,
        guest_docs_ttl_hours=s.guest_docs_ttl_hours,
    )


async def _visible(session: SessionDep, doc_id: str, visitor: str) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.visitor_id not in (None, visitor):
        raise HTTPException(404, NOT_FOUND)
    return doc


async def _check_quota(session: SessionDep, redis: RedisDep, ip: str, viewer: Viewer) -> None:
    s = get_settings()
    # Лимиты — для гостей демо: владелец пополняет базу клиники без ограничений
    if viewer.owner:
        return
    if await _own_count(session, viewer.visitor) >= s.guest_docs_limit:
        raise HTTPException(
            409,
            f"В демо можно загрузить до {s.guest_docs_limit} своих документов. "
            "Удалите один из загруженных, чтобы добавить новый.",
        )
    await hit_limit(redis, "upload", ip, s.uploads_per_hour)


@router.get("", response_model=DocumentList)
async def list_documents(session: SessionDep, viewer: ViewerDep):
    docs = await session.scalars(
        select(Document)
        .where(or_(Document.visitor_id.is_(None), Document.visitor_id == viewer.visitor))
        # Сначала свои документы (новые сверху), потом база клиники в порядке демо
        .order_by(Document.visitor_id.is_(None), Document.created_at.desc())
    )
    docs = list(docs)
    seed_order = list(SEED_BY_KEY)
    own = [d for d in docs if _owns(viewer, d)]
    base = sorted(
        (d for d in docs if not _owns(viewer, d)),
        key=lambda d: seed_order.index(d.seed_key) if d.seed_key in seed_order else 99,
    )
    return DocumentList(
        documents=[to_out(d, viewer) for d in own + base],
        limits=await _limits(session, viewer),
    )


@router.post("", response_model=DocumentOut, status_code=201)
async def upload(
    file: UploadFile,
    session: SessionDep,
    redis: RedisDep,
    embedder: EmbedderDep,
    ip: IpDep,
    viewer: ViewerDep,
):
    started = time.perf_counter()
    s = get_settings()
    filename = (file.filename or "документ").strip()[:255]
    try:
        kind = kind_of(filename)
    except ExtractError as e:
        raise HTTPException(415, str(e)) from e
    max_bytes = int(s.max_upload_mb * 1024 * 1024)
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            413, f"Файл больше {s.max_upload_mb:g} МБ — для демо это слишком много."
        )
    if not data:
        raise HTTPException(422, "Файл пустой.")
    await _check_quota(session, redis, ip, viewer)

    doc = Document(
        visitor_id=None if viewer.owner else viewer.visitor,
        title=filename.rsplit(".", 1)[0][:200],
        kind=kind,
        filename=filename,
        size_bytes=len(data),
    )
    session.add(doc)
    await session.commit()

    async def load() -> Extracted:
        return extract_file(kind, data, filename, s.max_pdf_pages)

    await ingest(session, embedder, doc, load, started)
    return to_out(doc, viewer)


@router.post("/url", response_model=DocumentOut, status_code=201)
async def upload_url(
    body: UrlIn,
    session: SessionDep,
    redis: RedisDep,
    embedder: EmbedderDep,
    ip: IpDep,
    viewer: ViewerDep,
):
    started = time.perf_counter()
    s = get_settings()
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    await _check_quota(session, redis, ip, viewer)

    doc = Document(
        visitor_id=None if viewer.owner else viewer.visitor,
        title=url[:200],
        kind="url",
        source_url=url,
    )
    session.add(doc)
    await session.commit()

    async def load() -> Extracted:
        data, kind = await fetch_page(
            url,
            allow_private=bool(s.allow_private_urls),
            max_bytes=int(s.max_upload_mb * 1024 * 1024),
        )
        doc.size_bytes = len(data)
        return extract_file(kind, data, url, s.max_pdf_pages)

    await ingest(session, embedder, doc, load, started)
    return to_out(doc, viewer)


@router.get("/{doc_id}/chunks", response_model=DocumentChunks)
async def chunks(doc_id: str, session: SessionDep, viewer: ViewerDep):
    doc = await _visible(session, doc_id, viewer.visitor)
    rows = await session.scalars(
        select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.position)
    )
    return DocumentChunks(
        document=to_out(doc, viewer),
        chunks=[
            ChunkOut(id=c.id, position=c.position, heading=c.heading, text=c.text) for c in rows
        ],
    )


@router.get("/{doc_id}/file")
async def original(doc_id: str, session: SessionDep):
    """Оригинал документа демо-базы. Свои файлы гостей не хранятся — только их фрагменты.
    Без X-Visitor-Id: ссылку открывают прямо в браузере."""
    doc = await session.get(Document, doc_id)
    seed = SEED_BY_KEY.get(doc.seed_key or "") if doc else None
    if seed is None or seed.kind == "url":
        raise HTTPException(404, NOT_FOUND)
    return FileResponse(seed.path, media_type=MEDIA_TYPES[seed.kind], filename=seed.file)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, session: SessionDep, viewer: ViewerDep):
    doc = await _visible(session, doc_id, viewer.visitor)
    if not _owns(viewer, doc):
        raise HTTPException(403, "Документы клиники — общая база демо, их удалить нельзя.")
    if doc.filename == ANSWERS_FILE:
        # Удалили документ с ответами — ответы администратора больше не нужны
        key = CLINIC_OWNER if doc.visitor_id is None else viewer.visitor
        await session.execute(delete(KbAnswer).where(KbAnswer.visitor_id == key))
    await session.delete(doc)
    await session.commit()
