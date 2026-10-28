"""Клиент Telegram Bot API: несколько методов поверх httpx, без отдельной библиотеки."""

import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

Markup = dict[str, Any]


class TelegramError(Exception):
    pass


def inline(rows: list[list[tuple[str, str]]]) -> Markup:
    """Кнопки под сообщением: [(текст, callback_data), …] по строкам."""
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row] for row in rows
        ]
    }


def keyboard(rows: list[list[str | dict[str, Any]]], placeholder: str | None = None) -> Markup:
    """Кнопки вместо клавиатуры: нажатие отправляет текст кнопки как сообщение клиента."""
    markup: Markup = {
        "keyboard": [[b if isinstance(b, dict) else {"text": b} for b in row] for row in rows],
        "resize_keyboard": True,
    }
    if placeholder:
        markup["input_field_placeholder"] = placeholder
    return markup


class TelegramClient:
    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0))

    async def _post(self, method: str, **kwargs: Any) -> Any:
        try:
            resp = await self._http.post(self._base + method, **kwargs)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            # from None: в тексте исходной ошибки httpx — адрес запроса с токеном бота
            raise TelegramError(f"{method}: Telegram недоступен ({e.__class__.__name__})") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', resp.status_code)}")
        return data["result"]

    async def call(self, method: str, **params: Any) -> Any:
        return await self._post(method, json={k: v for k, v in params.items() if v is not None})

    async def send(self, chat_id: int, text: str, markup: Markup | None = None) -> dict:
        return await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
            reply_markup=markup,
        )

    async def send_document(
        self, chat_id: int, document: str | Path, caption: str | None = None
    ) -> dict:
        """Файл с диска или уже загруженный в Telegram (file_id) — его не нужно слать снова."""
        if isinstance(document, str):
            return await self.call(
                "sendDocument", chat_id=chat_id, document=document, caption=caption
            )
        data = {"chat_id": str(chat_id), **({"caption": caption} if caption else {})}
        files = {"document": (document.name, document.read_bytes())}
        return await self._post("sendDocument", data=data, files=files)

    async def typing(self, chat_id: int) -> None:
        await self.call("sendChatAction", chat_id=chat_id, action="typing")

    async def answer(self, callback_id: str, text: str = "") -> None:
        await self.call("answerCallbackQuery", callback_query_id=callback_id, text=text or None)

    async def aclose(self) -> None:
        await self._http.aclose()


_client: TelegramClient | None = None


def get_telegram() -> TelegramClient | None:
    """Клиент бота или None, если токен не задан."""
    global _client
    token = get_settings().telegram_bot_token
    if not token:
        return None
    if _client is None:
        _client = TelegramClient(token)
    return _client


def set_telegram(client: TelegramClient | None) -> None:
    global _client
    _client = client
