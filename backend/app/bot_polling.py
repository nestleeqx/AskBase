"""Telegram-бот без вебхука: сам опрашивает Telegram (локально, сервис bot в Docker).

Запуск: python -m app.bot_polling
"""

import asyncio
import logging

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.embeddings import create_embedder
from app.llm import create_provider
from app.services.bot import BOT_COMMANDS, Bot
from app.services.redis_store import get_redis
from app.services.telegram import TelegramError, get_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx пишет адрес каждого запроса, а в адресе Bot API — токен бота
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

# Опрос с вебхуком несовместим: Telegram отдаёт обновления только одним способом
WEBHOOK_SET = (
    "У бота настроен вебхук %s — обновления уходят туда, и опрос их не получит. "
    "Для локальной проверки заведите отдельного бота или снимите вебхук (deleteWebhook)."
)


async def main() -> None:
    settings = get_settings()
    tg = get_telegram()
    if tg is None:
        log.info("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
        return
    await init_db()
    bot = Bot(SessionLocal, create_provider(settings), create_embedder(settings), get_redis(), tg)
    me = await tg.call("getMe")
    await tg.call("setMyCommands", commands=BOT_COMMANDS)
    log.info("Бот @%s слушает сообщения", me["username"])

    offset = 0
    # Ссылки на задачи держим, иначе сборщик мусора может прервать их посреди ответа
    tasks: set[asyncio.Task] = set()
    while True:
        try:
            info = await tg.call("getWebhookInfo")
            if info.get("url"):
                log.warning(WEBHOOK_SET, info["url"])
                await asyncio.sleep(60)
                continue
            updates = await tg.call(
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
        except TelegramError as e:
            log.warning("Telegram: %s", e)
            await asyncio.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            # Сообщения обрабатываются параллельно: долгий ответ одному клиенту не держит других
            task = asyncio.create_task(bot.handle(update))
            tasks.add(task)
            task.add_done_callback(tasks.discard)


if __name__ == "__main__":
    asyncio.run(main())
