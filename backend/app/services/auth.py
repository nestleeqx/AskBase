"""Вход владельца клиники: пароль из OWNER_PASSWORD → подписанный токен на 30 дней.

Гостю вход не нужен: он смотрит демо, пишет в тестовый чат и пробует всё на своих данных.
Владелец меняет то, что видят все клиенты: документы клиники и настройки бота, — и видит
все диалоги. Сменили пароль — старые токены перестают работать.
"""

import hashlib
import hmac
import time

from app.config import get_settings

TOKEN_DAYS = 30


def _key() -> bytes:
    return hashlib.sha256(f"askbase-owner:{get_settings().owner_password}".encode()).digest()


def _sign(expires: int) -> str:
    return hmac.new(_key(), str(expires).encode(), hashlib.sha256).hexdigest()[:40]


def owner_enabled() -> bool:
    return bool(get_settings().owner_password)


def check_password(password: str) -> bool:
    expected = get_settings().owner_password
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def make_token() -> str:
    expires = int(time.time()) + TOKEN_DAYS * 24 * 3600
    return f"{expires}.{_sign(expires)}"


def valid_token(token: str | None) -> bool:
    if not token or not owner_enabled():
        return False
    expires, _, signature = token.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(signature, _sign(int(expires)))
