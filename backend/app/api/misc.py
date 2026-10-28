from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.deps import SessionDep
from app.services.indexing import cleanup_guest_docs

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/cron/cleanup")
async def cron_cleanup(session: SessionDep, authorization: str | None = Header(default=None)):
    """Ночная очистка своих документов гостей старше суток (Vercel Cron)."""
    s = get_settings()
    if not s.cron_secret or authorization != f"Bearer {s.cron_secret}":
        raise HTTPException(401, "Нужен CRON_SECRET")
    return {"removed": await cleanup_guest_docs(session, s.guest_docs_ttl_hours)}
