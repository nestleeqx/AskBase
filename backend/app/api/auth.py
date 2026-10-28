from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.deps import IpDep, RedisDep, ViewerDep
from app.services.auth import check_password, make_token, owner_enabled
from app.services.redis_store import hit_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Подбор пароля: не больше 10 попыток в час с одного адреса
LOGIN_ATTEMPTS = 10


class AuthStatus(BaseModel):
    owner: bool
    # Пароль владельца задан на сервере — вход владельца доступен
    owner_enabled: bool


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    token: str


@router.get("", response_model=AuthStatus)
async def status(viewer: ViewerDep):
    return AuthStatus(owner=viewer.owner, owner_enabled=owner_enabled())


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, redis: RedisDep, ip: IpDep):
    if not owner_enabled():
        raise HTTPException(403, "Вход владельца в этом демо не настроен. Войдите как гость.")
    await hit_limit(redis, "login", ip, LOGIN_ATTEMPTS)
    if not check_password(body.password):
        raise HTTPException(401, "Неверный пароль.")
    return LoginOut(token=make_token())
