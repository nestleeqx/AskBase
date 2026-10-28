import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.embeddings import EmbeddingProvider
from app.llm import LLMProvider
from app.models import CLINIC_OWNER
from app.services.auth import valid_token
from app.services.redis_store import get_redis

_VISITOR_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def visitor_id(x_visitor_id: Annotated[str | None, Header()] = None) -> str:
    """Анонимный id посетителя из localStorage: его документы видит только он."""
    if not x_visitor_id or not _VISITOR_RE.match(x_visitor_id):
        raise HTTPException(400, "Не удалось определить сессию. Обновите страницу.")
    return x_visitor_id


@dataclass(frozen=True)
class Viewer:
    """Кто смотрит админку: гость демо (по id из localStorage) или владелец клиники."""

    visitor: str
    owner: bool

    @property
    def profile_key(self) -> str:
        """Чьи настройки бота меняет: владелец — общие для всех клиентов, гость — свои."""
        return CLINIC_OWNER if self.owner else self.visitor


def viewer(
    visitor: Annotated[str, Depends(visitor_id)],
    x_owner_token: Annotated[str | None, Header()] = None,
) -> Viewer:
    return Viewer(visitor=visitor, owner=valid_token(x_owner_token))


def get_embedder(request: Request) -> EmbeddingProvider:
    return request.app.state.embedder


def get_llm(request: Request) -> LLMProvider:
    return request.app.state.llm


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
IpDep = Annotated[str, Depends(client_ip)]
VisitorDep = Annotated[str, Depends(visitor_id)]
ViewerDep = Annotated[Viewer, Depends(viewer)]
EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]
LLMDep = Annotated[LLMProvider, Depends(get_llm)]
