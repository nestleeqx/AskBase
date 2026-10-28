"""Уведомления менеджеру клиники в Telegram: заявки на запись и вопросы, которые ждут человека."""

import logging
from html import escape

from app.config import get_settings
from app.services.telegram import TelegramClient, TelegramError

log = logging.getLogger(__name__)


def dialog_url(conversation_id: str) -> str | None:
    """Ссылка на диалог в админке. Telegram принимает в кнопках только https — локально без неё."""
    url = f"{get_settings().public_site_url}/admin/dialogs?id={conversation_id}"
    return url if url.startswith("https://") else None


def client_line(title: str, username: str | None) -> str:
    return escape(title) + (f" (@{escape(username)})" if username else "")


# Первая строка каждого уведомления: в демо менеджер часто сам пишет боту как клиент,
# и уведомление приходит в тот же чат — его не должно быть легко спутать с ответом клиенту
HEADER = "🔔 <i>Для администратора клиники</i>"


async def notify_manager(tg: TelegramClient, text: str, conversation_id: str) -> None:
    """Сообщение в чат менеджера. Ошибка Telegram не мешает ответить клиенту — только в лог."""
    chat_id = get_settings().manager_chat_id
    if not chat_id:
        return
    url = dialog_url(conversation_id)
    markup = {"inline_keyboard": [[{"text": "Открыть диалог", "url": url}]]} if url else None
    try:
        await tg.send(chat_id, f"{HEADER}\n{text}", markup)
    except TelegramError as e:
        log.warning("Уведомление менеджеру не отправлено: %s", e)
