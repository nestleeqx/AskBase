"""Telegram-бот клиники: ответы по базе знаний, цены, запись на приём, связь с администратором.

Обновления приходят одинаково из опроса (локально, сервис bot) и из вебхука (на проде).
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from html import escape
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.embeddings import EmbeddingProvider
from app.llm import LLMProvider
from app.models import Booking, Conversation, Message, TelegramChat, now
from app.services import booking
from app.services.answer import sources_line
from app.services.dialogs import ask
from app.services.prompts import CLINIC
from app.services.redis_store import PREFIX, RateLimitExceeded, hit_limit
from app.services.seed import SEED_BY_KEY
from app.services.telegram import Markup, TelegramClient, TelegramError, inline, keyboard

log = logging.getLogger(__name__)

# --- Кнопки ---

PRICES = "💰 Цены"
BOOK = "📅 Записаться"
OPERATOR = "👤 Связаться с администратором"
CANCEL = "Отмена"
SKIP = "Пропустить"
SHARE_PHONE = "📱 Поделиться номером"

MENU = keyboard([[PRICES, BOOK], [OPERATOR]], placeholder="Напишите вопрос…") | {
    "is_persistent": True
}

# Разделы прайса: кнопка → вопрос боту. Ответ собирает тот же поиск по документам,
# поэтому цены всегда из актуального прайс-листа
PRICE_TOPICS = {
    "diag": ("Консультации и снимки", "Сколько стоят консультации и снимки зубов?"),
    "hygiene": ("Чистка и отбеливание", "Сколько стоят профессиональная чистка и отбеливание?"),
    "therapy": ("Лечение кариеса и каналов", "Сколько стоит лечение кариеса и пульпита?"),
    "surgery": ("Удаление зубов", "Сколько стоит удаление зуба, в том числе зуба мудрости?"),
    "implants": ("Имплантация", "Сколько стоит имплантация зуба?"),
    "prosthetics": ("Коронки, виниры, протезы", "Сколько стоят коронки, виниры и протезы?"),
    "ortho": ("Брекеты и элайнеры", "Сколько стоят брекеты и элайнеры?"),
    "kids": ("Детская стоматология", "Сколько стоит лечение зубов у ребёнка?"),
}
PRICE_PDF = "pdf"


def _price_buttons() -> Markup:
    items = [(label, f"price:{key}") for key, (label, _) in PRICE_TOPICS.items()]
    rows = [items[i : i + 2] for i in range(0, len(items), 2)]
    rows.append([("📄 Весь прайс-лист (PDF)", f"price:{PRICE_PDF}")])
    return inline(rows)


# --- Тексты ---

GREETING = (
    f"Здравствуйте! Я бот стоматологической клиники «{CLINIC}».\n\n"
    "Отвечаю на вопросы о ценах, врачах, подготовке к процедурам и записи — "
    "по документам клиники. Напишите вопрос своими словами или выберите кнопку внизу."
)
PRICES_TEXT = (
    "Назову цену любой услуги по прайс-листу — просто напишите, что интересует. "
    "Например: «Сколько стоит удалить зуб мудрости?»\n\nИли выберите раздел:"
)
TEXT_ONLY = "Я понимаю только текст — напишите, пожалуйста, вопрос словами."
SORRY = "Не получилось ответить — попробуйте ещё раз через минуту."

BOOK_START = (
    "Запишу вас на приём — это четыре коротких вопроса. "
    "Администратор позвонит в рабочее время и подтвердит время визита.\n\n"
    "Как вас зовут?"
)
NAME_INVALID = "Напишите, пожалуйста, имя — например, «Анна»."
ASK_PHONE = (
    "Приятно познакомиться, {name}! Оставьте телефон для связи — "
    "нажмите кнопку ниже или напишите номер."
)
PHONE_INVALID = (
    "Не похоже на номер телефона. Напишите его в виде +7 900 123-45-67 "
    "или нажмите «Поделиться номером»."
)
ASK_REASON = (
    "Что беспокоит или на какую услугу хотите записаться? Можно коротко: «болит зуб», "
    "«чистка», «консультация по имплантам». Так администратор подберёт врача."
)
ASK_TIME = (
    "Когда вам удобно прийти? Например: «завтра после 18:00» или «в субботу утром».\n\n"
    "Клиника работает {hours}."
)
TOO_LONG = "Слишком длинно — напишите, пожалуйста, короче."
BOOK_CANCELLED = "Хорошо, запись отменена. Если появятся вопросы — пишите."
NOTHING_TO_CANCEL = "Отменять нечего. Задайте вопрос или выберите кнопку внизу."


def _book_done(b: Booking) -> str:
    rows = [("Имя", b.name), ("Телефон", b.phone)]
    if b.reason:
        rows.append(("Повод", b.reason))
    rows.append(("Удобное время", b.preferred_time))
    lines = "\n".join(f"{label}: {escape(value)}" for label, value in rows)
    return (
        f"<b>Заявка на запись принята ✅</b>\n\n{lines}\n\n"
        "Администратор позвонит вам в рабочее время и подтвердит запись. "
        "Если планы изменятся — просто напишите сюда."
    )


def _operator_text() -> str:
    s = get_settings()
    return (
        "Передал ваш запрос администратору — он ответит прямо в этом чате. "
        f"Администратор на связи {s.clinic_hours}.\n\n"
        f"Если вопрос срочный — позвоните: {s.clinic_phone}."
    )


def booking_summary(b: Booking) -> str:
    """Заявка одной строкой — сообщение в истории диалога для администратора."""
    parts = [b.name, b.phone, *([b.reason] if b.reason else []), f"удобно: {b.preferred_time}"]
    return "Заявка на запись: " + ", ".join(parts)


def reply_html(text: str, sources: list[dict] | None, title: str | None = None) -> str:
    """Ответ бота для Telegram: заголовок раздела, текст и строка с источником курсивом."""
    parts = [f"<b>{escape(title)}</b>"] if title else []
    parts.append(escape(text))
    line = sources_line([s["title"] for s in sources or []])
    if line:
        parts.append(f"\n<i>{escape(line)}</i>")
    return "\n".join(parts)


def _chat_title(chat: dict[str, Any]) -> str:
    name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
    return name or (f"@{chat['username']}" if chat.get("username") else "Клиент в Telegram")


@dataclass
class Bot:
    sessions: async_sessionmaker
    llm: LLMProvider
    embedder: EmbeddingProvider
    redis: Redis
    tg: TelegramClient

    async def handle(self, update: dict[str, Any]) -> None:
        chat_id = None
        try:
            if "callback_query" in update:
                query = update["callback_query"]
                chat_id = (query.get("message") or {}).get("chat", {}).get("id")
                await self._on_button(query)
            elif "message" in update:
                chat_id = update["message"]["chat"]["id"]
                await self._on_message(update["message"])
        except TelegramError as e:
            log.warning("Telegram: %s", e)
        except Exception:
            log.exception("Не удалось обработать обновление %s", update.get("update_id"))
            if chat_id is not None:
                try:
                    await self.tg.send(chat_id, SORRY)
                except TelegramError:
                    pass

    # --- Сообщения ---

    async def _on_message(self, msg: dict[str, Any]) -> None:
        chat = msg["chat"]
        # Бот для клиентов: в группах не отвечает
        if chat.get("type") != "private":
            return
        chat_id = chat["id"]
        text = (msg.get("text") or "").strip()
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""

        if command in {"/start", "/help"}:
            await booking.clear_state(self.redis, chat_id)
            await self.tg.send(chat_id, GREETING, MENU)
            return
        if command == "/cancel" or (text == CANCEL and command == ""):
            cancelled = await booking.clear_state(self.redis, chat_id)
            await self.tg.send(chat_id, BOOK_CANCELLED if cancelled else NOTHING_TO_CANCEL, MENU)
            return

        state = await booking.get_state(self.redis, chat_id)
        if state is not None:
            await self._booking_step(msg, state)
        elif not text:
            await self.tg.send(chat_id, TEXT_ONLY)
        elif text == PRICES:
            await self.tg.send(chat_id, PRICES_TEXT, _price_buttons())
        elif text == BOOK:
            await self._booking_start(msg)
        elif text == OPERATOR:
            await self._operator(chat)
        elif command:
            await self.tg.send(chat_id, GREETING, MENU)
        else:
            await self._question(chat, text)

    async def _conversation(self, session: AsyncSession, chat: dict[str, Any]) -> Conversation:
        """Диалог чата: заводится при первом сообщении, имя клиента обновляется."""
        row = await session.get(TelegramChat, chat["id"])
        if row is None:
            conv = Conversation(channel="telegram")
            session.add(conv)
            await session.flush()
            row = TelegramChat(chat_id=chat["id"], conversation_id=conv.id, title="")
            session.add(row)
        else:
            conv = await session.get(Conversation, row.conversation_id)
        row.title, row.username = _chat_title(chat), chat.get("username")
        return conv

    async def _keep_typing(self, chat_id: int) -> None:
        # «печатает…» в Telegram гаснет через 5 секунд — продлеваем, пока бот думает
        try:
            while True:
                await self.tg.typing(chat_id)
                await asyncio.sleep(4)
        except TelegramError:
            pass

    async def _question(
        self, chat: dict[str, Any], text: str, title: str | None = None, use_history: bool = True
    ) -> None:
        s = get_settings()
        chat_id = chat["id"]
        question = " ".join(text.split())
        if len(question) > s.max_question_chars:
            await self.tg.send(
                chat_id, f"Сообщение длиннее {s.max_question_chars} символов — сократите его."
            )
            return
        try:
            await hit_limit(self.redis, "chat", f"tg:{chat_id}", s.questions_per_hour)
        except RateLimitExceeded as e:
            minutes = max(1, e.retry_after // 60)
            await self.tg.send(
                chat_id, f"Лимит демо: {e.limit} вопросов в час. Попробуйте через {minutes} мин."
            )
            return

        typing = asyncio.create_task(self._keep_typing(chat_id))
        try:
            async with self.sessions() as session:
                conv = await self._conversation(session, chat)
                # visitor пуст: в Telegram видны только документы клиники, не свои документы гостей
                _, reply = await ask(
                    session, self.llm, self.embedder, self.redis, conv, question, "", use_history
                )
        finally:
            typing.cancel()
        await self.tg.send(chat_id, reply_html(reply.text, reply.sources, title))

    async def _log(self, chat: dict[str, Any], *messages: Message) -> None:
        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            for m in messages:
                m.conversation_id = conv.id
            session.add_all(messages)
            conv.updated_at = now()
            await session.commit()

    async def _operator(self, chat: dict[str, Any]) -> None:
        text = _operator_text()
        await self._log(
            chat,
            Message(role="user", text=OPERATOR),
            Message(role="bot", text=text, reason="operator", topic="other"),
        )
        await self.tg.send(chat["id"], text, MENU)

    # --- Кнопки под сообщениями ---

    async def _on_button(self, query: dict[str, Any]) -> None:
        data = query.get("data") or ""
        chat = (query.get("message") or {}).get("chat") or {}
        await self.tg.answer(query["id"])
        kind, _, key = data.partition(":")
        if kind != "price" or chat.get("type") != "private":
            return
        if key == PRICE_PDF:
            await self._send_price_list(chat["id"])
        elif key in PRICE_TOPICS:
            label, question = PRICE_TOPICS[key]
            await self._question(chat, question, title=label, use_history=False)

    async def _send_price_list(self, chat_id: int) -> None:
        """PDF из демо-базы. Загруженный раз файл Telegram хранит у себя — дальше шлём его id."""
        path = SEED_BY_KEY["prajs"].path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        key = f"{PREFIX}tg:file:{get_settings().telegram_webhook_secret[:12]}:{digest}"
        caption = f"Прайс-лист клиники «{CLINIC}»"
        file_id = await self.redis.get(key)
        if file_id:
            await self.tg.send_document(chat_id, file_id, caption)
            return
        sent = await self.tg.send_document(chat_id, path, caption)
        await self.redis.set(key, sent["document"]["file_id"], ex=30 * 24 * 3600)

    # --- Запись на приём ---

    async def _booking_start(self, msg: dict[str, Any]) -> None:
        chat_id = msg["chat"]["id"]
        await booking.save_state(self.redis, chat_id, {"step": "name"})
        sender = msg.get("from") or {}
        name = booking.valid_name(sender.get("first_name") or "")
        rows = [[name], [CANCEL]] if name else [[CANCEL]]
        await self.tg.send(chat_id, BOOK_START, keyboard(rows, placeholder="Ваше имя"))

    async def _ask_step(self, chat_id: int, state: dict[str, Any], prefix: str = "") -> None:
        step = state["step"]
        if step == "name":
            text, markup = "Как вас зовут?", keyboard([[CANCEL]], placeholder="Ваше имя")
        elif step == "phone":
            text = ASK_PHONE.format(name=escape(state["name"]))
            share = {"text": SHARE_PHONE, "request_contact": True}
            markup = keyboard([[share], [CANCEL]], placeholder="+7 900 123-45-67")
        elif step == "reason":
            text, markup = ASK_REASON, keyboard([[SKIP], [CANCEL]], placeholder="Что беспокоит")
        else:
            text = ASK_TIME.format(hours=get_settings().clinic_hours)
            markup = keyboard(
                [["Утром", "Днём", "Вечером"], ["В ближайшее время"], [CANCEL]],
                placeholder="Удобное время",
            )
        await self.tg.send(chat_id, f"{prefix}\n\n{text}" if prefix else text, markup)

    async def _booking_step(self, msg: dict[str, Any], state: dict[str, Any]) -> None:
        chat_id = msg["chat"]["id"]
        text = booking.clean(msg.get("text") or "")
        step = state["step"]
        contact = msg.get("contact")

        if not text and not (step == "phone" and contact):
            await self._ask_step(chat_id, state, TEXT_ONLY)
            return

        if step == "name":
            name = booking.valid_name(text)
            if name is None:
                await self.tg.send(chat_id, NAME_INVALID)
                return
            state.update(name=name, step="phone")
        elif step == "phone":
            phone = booking.normalize_phone(contact["phone_number"] if contact else text)
            if phone is None and contact:
                phone = "+" + "".join(c for c in contact["phone_number"] if c.isdigit())
            if phone is None:
                await self.tg.send(chat_id, PHONE_INVALID)
                return
            state.update(phone=phone, step="reason")
        elif step == "reason":
            if len(text) > 300:
                await self.tg.send(chat_id, TOO_LONG)
                return
            state.update(reason=None if text == SKIP else text, step="time")
        else:
            if len(text) > 200:
                await self.tg.send(chat_id, TOO_LONG)
                return
            await self._booking_done(msg["chat"], state, text)
            return

        await booking.save_state(self.redis, chat_id, state)
        await self._ask_step(chat_id, state)

    async def _booking_done(self, chat: dict[str, Any], state: dict[str, Any], time: str) -> None:
        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            b = Booking(
                conversation_id=conv.id,
                name=state["name"],
                phone=state["phone"],
                reason=state.get("reason"),
                preferred_time=time,
            )
            session.add(b)
            session.add_all(
                [
                    Message(conversation_id=conv.id, role="user", text=BOOK),
                    Message(
                        conversation_id=conv.id,
                        role="bot",
                        text=booking_summary(b),
                        reason="booking",
                        topic="booking",
                    ),
                ]
            )
            conv.updated_at = now()
            await session.commit()
        await booking.clear_state(self.redis, chat["id"])
        await self.tg.send(chat["id"], _book_done(b), MENU)
