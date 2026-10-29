"""Telegram-бот клиники: ответы по базе знаний, цены, запись на приём, связь с администратором.

Обновления приходят одинаково из опроса (локально, сервис bot) и из вебхука (на проде).
"""

import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.embeddings import EmbeddingProvider
from app.llm import LLMProvider
from app.models import Booking, Conversation, Message, TelegramChat, now
from app.services import booking
from app.services.answer import sources_line
from app.services.dialogs import ask
from app.services.notify import client_line, notify_manager
from app.services.profile import DEFAULT_GREETING, Profile, default_profile, profile_for
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

# Команды в меню Telegram: ставятся при запуске опроса и при установке вебхука
BOT_COMMANDS = [
    {"command": "start", "description": "Начать сначала"},
    {"command": "cancel", "description": "Отменить запись"},
]

# Приветствие по умолчанию; своё задаётся в настройках бота
GREETING = DEFAULT_GREETING
PRICES_TEXT = (
    "Назову цену любой услуги по прайс-листу — просто напишите, что интересует. "
    "Например: «Сколько стоит удалить зуб мудрости?»\n\nИли выберите раздел:"
)
TEXT_ONLY = "Я понимаю только текст — напишите, пожалуйста, вопрос словами."
SORRY = "Не получилось ответить — попробуйте ещё раз через минуту."

BOOK_INTRO = (
    "Запишу вас на приём. Администратор позвонит в рабочее время и подтвердит время визита."
)
BOOK_START = f"{BOOK_INTRO}\n\nКак вас зовут?"
BOOK_EDIT_INTRO = "Изменим вашу заявку."
OPEN_BOOKING = {
    "new": "У вас уже есть заявка на запись — администратор ещё не звонил:",
    "confirmed": "У вас уже есть запись — администратор её подтвердил:",
}
# Подтверждённая заявка считается открытой две недели: более старая — уже прошедший визит
CONFIRMED_DAYS = 14


def choice_buttons(confirmed: bool) -> Markup:
    edit = "✏️ Перенести или изменить" if confirmed else "✏️ Изменить эту заявку"
    return inline(
        [
            [(edit, "bk:edit")],
            [("➕ Записать ещё одного человека", "bk:new")],
            [("Оставить как есть", "bk:keep")],
        ]
    )


NOTHING_CHANGED = {
    "new": (
        "Ничего не поменялось — заявка остаётся прежней. Администратор позвонит в рабочее время."
    ),
    "confirmed": "Ничего не поменялось — запись остаётся прежней. Ждём вас в клинике!",
}
# Та же заявка второй раз («➕ Записать ещё одного человека», а имя и время прежние)
ALREADY_BOOKED = {
    "new": "Такая заявка уже есть — повторно не создаю. Администратор позвонит в рабочее время.",
    "confirmed": "Вы уже записаны на это время — повторно не создаю. Ждём вас в клинике!",
}
BOOK_KEPT = {
    "new": "Хорошо, заявка остаётся как есть. Администратор позвонит в рабочее время.",
    "confirmed": "Хорошо, запись остаётся как есть. Ждём вас в клинике!",
}
# Сообщение бота в истории диалога, когда клиент попросил записать его своими словами
BOOK_FROM_TEXT = "Начал запись на приём по шагам."
NAME_INVALID = "Напишите, пожалуйста, имя — например, «Анна»."
ASK_PHONE = "Оставьте телефон для связи — нажмите кнопку ниже или напишите номер."
# Только сразу после того, как клиент назвал имя на шаге записи
GREET = "Приятно познакомиться, {name}! "
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
NOTHING_TO_CANCEL = (
    "Активных записей нет — отменять нечего. Записаться — кнопкой «📅 Записаться» внизу."
)
CANCEL_BUTTONS = inline([[("❌ Да, отменить запись", "bk:cancel")], [("Нет, оставить", "bk:stay")]])
# Сообщение бота в истории диалога, когда клиент попросил отменить запись словами
CANCEL_ASKED = "Спросил, отменить ли запись."
BOOKING_CANCELLED_DONE = (
    "Запись отменена. Если захотите прийти — нажмите «📅 Записаться» или напишите сюда."
)


LINKED = (
    "Готово, чат подключён к демо-админке ✅\n"
    "Ваша переписка с ботом теперь видна в разделе «Диалоги» — оттуда можно ответить себе "
    "как администратор клиники."
)
LINK_EXPIRED = (
    "Ссылка для подключения к админке устарела. Откройте раздел «Диалоги» в админке "
    "и нажмите «Подключить Telegram» ещё раз."
)
LINK_TTL = 30 * 60


def _link_key(token: str) -> str:
    return f"{PREFIX}tg:link:{token}"


async def create_link_token(redis: Redis, visitor_id: str) -> str:
    """Одноразовый токен для ссылки t.me/<бот>?start=<токен>: по нему чат найдёт посетителя."""
    token = secrets.token_urlsafe(16)
    await redis.set(_link_key(token), visitor_id, ex=LINK_TTL)
    return token


async def bot_username(redis: Redis, tg: TelegramClient) -> str:
    """Имя бота для ссылок — из getMe, с кешем на сутки."""
    key = f"{PREFIX}tg:me:{get_settings().telegram_webhook_secret[:12]}"
    cached = await redis.get(key)
    if cached:
        return cached
    me = await tg.call("getMe")
    await redis.set(key, me["username"], ex=24 * 3600)
    return me["username"]


async def ensure_webhook(redis: Redis, tg: TelegramClient, host: str = "") -> None:
    """На Vercel ставит вебхук на постоянный адрес проекта и раз в час проверяет его.

    host — адрес, на который пришёл запрос: запасной вариант, если Vercel не передал свой.
    Локально вебхук не нужен — бот опрашивает Telegram сам (сервис bot в Docker).
    """
    s = get_settings()
    host = s.vercel_project_production_url or host
    if not s.vercel or not host:
        return
    url = f"https://{host}/api/telegram/webhook"
    key = f"{PREFIX}tg:webhook:{s.telegram_webhook_secret[:12]}"
    if await redis.get(key) == url:
        return
    await tg.call(
        "setWebhook",
        url=url,
        secret_token=s.telegram_webhook_secret,
        allowed_updates=["message", "callback_query"],
    )
    await tg.call("setMyCommands", commands=BOT_COMMANDS)
    await redis.set(key, url, ex=3600)
    log.info("Вебхук Telegram: %s", url)


def operator_active(conv: Conversation) -> bool:
    return conv.operator_until is not None and conv.operator_until > now()


def _client(chat: dict[str, Any]) -> str:
    return client_line(_chat_title(chat), chat.get("username"))


def _booking_lines(b: Booking) -> str:
    rows = [("Имя", b.name), ("Телефон", b.phone)]
    if b.reason:
        rows.append(("Повод", b.reason))
    rows.append(("Удобное время", b.preferred_time))
    return "\n".join(f"{label}: {escape(value)}" for label, value in rows)


def _booking_lines_partial(state: dict[str, Any]) -> str:
    """То, что клиент уже сообщил для записи, — строками «Имя: Игорь»."""
    rows = [
        ("Имя", state.get("name")),
        ("Телефон", state.get("phone")),
        ("Повод", state.get("reason")),
        ("Удобное время", state.get("time")),
    ]
    return "\n".join(f"{label}: {escape(value)}" for label, value in rows if value)


def _book_done(b: Booking, edited: bool = False) -> str:
    header = "Заявка обновлена ✅" if edited else "Заявка на запись принята ✅"
    if b.status == "confirmed":
        # Время то же — запись остаётся подтверждённой
        tail = "Время записи прежнее — ждём вас в клинике!"
    else:
        tail = (
            "Администратор позвонит вам в рабочее время и подтвердит запись. "
            "Если планы изменятся — просто напишите сюда."
        )
    return f"<b>{header}</b>\n\n{_booking_lines(b)}\n\n{tail}"


def _operator_text(profile: Profile | None = None) -> str:
    p = profile or default_profile()
    return (
        "Передал ваш запрос администратору — он ответит прямо в этом чате. "
        f"Администратор на связи {p.hours}.\n\n"
        f"Если вопрос срочный — позвоните: {p.phone}."
    )


# Начало строки в истории диалога — по нему админка подписывает сообщение о записи
BOOKING_NOTES = {
    "new": "Заявка на запись: ",
    "edited": "Заявка изменена: ",
    "kept": "Запись без изменений: ",
    "cancelled": "Клиент отменил запись: ",
}
BOOKING_CANCELLED_NOTE = "Клиент отменил запись по шагам."


def booking_summary(
    b: Booking, edited: bool = False, kept: bool = False, cancelled: bool = False
) -> str:
    """Заявка одной строкой — сообщение в истории диалога для администратора."""
    parts = [b.name, b.phone, *([b.reason] if b.reason else []), f"удобно: {b.preferred_time}"]
    kind = "cancelled" if cancelled else "kept" if kept else "edited" if edited else "new"
    return BOOKING_NOTES[kind] + ", ".join(parts)


# Сколько дней «Я записан?» помнит прошлые заявки
STATUS_DAYS = 30


async def _latest_booking(session: AsyncSession, conversation_id: str) -> Booking | None:
    since = now() - timedelta(days=STATUS_DAYS)
    return await session.scalar(
        select(Booking)
        .where(Booking.conversation_id == conversation_id, Booking.created_at >= since)
        .order_by(Booking.created_at.desc())
        .limit(1)
    )


def booking_status_text(b: Booking | None) -> str:
    """Ответ на «Я записан?» — обычным текстом: он же сохраняется в истории диалога."""
    if b is None:
        return "Заявок на запись от вас пока нет. Записаться — кнопкой «📅 Записаться» внизу."
    lines = [f"Имя: {b.name}", f"Телефон: {b.phone}"]
    if b.reason:
        lines.append(f"Повод: {b.reason}")
    lines.append(f"Удобное время: {b.preferred_time}")
    details = "\n".join(lines)
    if b.status == "confirmed":
        return (
            f"Да, вы записаны — администратор подтвердил запись:\n\n{details}\n\n"
            "Ждём вас в клинике! Если планы изменятся — отправьте /cancel или напишите сюда."
        )
    if b.status == "new":
        return (
            f"Ваша заявка на запись принята, администратор ещё не звонил:\n\n{details}\n\n"
            "Он позвонит в рабочее время и подтвердит время визита."
        )
    return (
        f"Ваша последняя запись отменена:\n\n{details}\n\n"
        "Записаться снова — кнопкой «📅 Записаться» внизу."
    )


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
            arg = text.split(maxsplit=1)[1] if " " in text else ""
            if command == "/start" and arg:
                await self._link(chat, arg.strip())
            else:
                await self.tg.send(chat_id, (await self._profile(chat_id)).greeting, MENU)
            return
        if command == "/myid":
            await self.tg.send(chat_id, f"ID этого чата: <code>{chat_id}</code>")
            return
        if command == "/cancel" or (text == CANCEL and command == ""):
            state = await booking.get_state(self.redis, chat_id)
            await booking.clear_state(self.redis, chat_id)
            if state is None:
                # Записи по шагам нет — значит, клиент хочет отменить уже оформленную запись
                await self._ask_cancel(chat_id)
            elif state.get("step") == "confirm_cancel":
                await self._remove_buttons(chat_id, state.get("message_id"))
                await self.tg.send(
                    chat_id, BOOK_KEPT.get(state.get("status"), BOOK_KEPT["new"]), MENU
                )
            elif state.get("step") == "choose":
                # «Отмена» вместо ответа на «У вас уже есть запись» — запись остаётся как есть
                await self._remove_buttons(chat_id, state.get("message_id"))
                await self._note_kept(chat_id, state)
                await self.tg.send(
                    chat_id, BOOK_KEPT.get(state.get("status"), BOOK_KEPT["new"]), MENU
                )
            elif state.get("edit_id"):
                # Отменили правку заявки, а не саму запись — прежняя заявка остаётся
                async with self.sessions() as session:
                    old = await session.get(Booking, state["edit_id"])
                if old is not None and old.status != "cancelled":
                    await self._note(chat_id, booking_summary(old, kept=True))
                    await self.tg.send(chat_id, BOOK_KEPT.get(old.status, BOOK_KEPT["new"]), MENU)
                else:
                    await self.tg.send(chat_id, BOOK_CANCELLED, MENU)
            else:
                await self._note(chat_id, BOOKING_CANCELLED_NOTE)
                await self.tg.send(chat_id, BOOK_CANCELLED, MENU)
            return

        state = await booking.get_state(self.redis, chat_id)
        if state is not None and state.get("step") in {"choose", "confirm_cancel"}:
            # Вместо ответа на «У вас уже есть запись» или «Отменить запись?» клиент нажал меню
            # или написал другое — оставляем запись как есть и делаем то, о чём он просит сейчас
            await self._leave_choice(chat_id, state)
            state = None
        if state is not None:
            await self._booking_step(msg, state)
        elif not text:
            await self.tg.send(chat_id, TEXT_ONLY)
        elif text == PRICES:
            await self.tg.send(chat_id, PRICES_TEXT, _price_buttons())
        elif text == BOOK:
            await self._booking_start(chat, msg.get("from") or {})
        elif text == OPERATOR:
            await self._operator(chat)
        elif command:
            await self.tg.send(chat_id, (await self._profile(chat_id)).greeting, MENU)
        else:
            await self._question(chat, text, sender=msg.get("from"))

    async def _profile(self, chat_id: int) -> Profile:
        """Настройки бота для этого чата: свои у гостя, подключившего чат к админке, иначе общие."""
        async with self.sessions() as session:
            visitor = await session.scalar(
                select(Conversation.visitor_id)
                .join(TelegramChat, TelegramChat.conversation_id == Conversation.id)
                .where(TelegramChat.chat_id == chat_id)
            )
            return await profile_for(session, visitor)

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

    async def _link(self, chat: dict[str, Any], token: str) -> None:
        """/start <токен> из админки: чат привязывается к посетителю, и тот видит свой диалог."""
        visitor = await self.redis.getdel(_link_key(token))
        if visitor is None:
            greeting = (await self._profile(chat["id"])).greeting
            await self.tg.send(chat["id"], f"{LINK_EXPIRED}\n\n{greeting}", MENU)
            return
        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            # Чат мог быть привязан к другому посетителю — теперь он принадлежит этому
            conv.visitor_id = visitor
            await session.commit()
        greeting = (await self._profile(chat["id"])).greeting
        await self.tg.send(chat["id"], f"{LINKED}\n\n{greeting}", MENU)

    async def _question(
        self,
        chat: dict[str, Any],
        text: str,
        title: str | None = None,
        use_history: bool = True,
        sender: dict[str, Any] | None = None,
    ) -> None:
        s = get_settings()
        chat_id = chat["id"]
        question = " ".join(text.split())
        if len(question) > s.max_question_chars:
            await self.tg.send(
                chat_id, f"Сообщение длиннее {s.max_question_chars} символов — сократите его."
            )
            return

        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            # Отвечает администратор: бот молчит, сообщение ждёт человека в админке.
            # Кнопки цен — справка, а не разговор, на них бот отвечает и сейчас
            if use_history and operator_active(conv):
                session.add(Message(conversation_id=conv.id, role="user", text=question))
                conv.updated_at = now()
                conv.waiting_since = conv.waiting_since or now()
                conv.attention_at = now()
                await session.commit()
                await notify_manager(
                    self.tg,
                    f"💬 <b>Новое сообщение</b>\n{_client(chat)}: «{escape(question)}»",
                    conv.id,
                )
                return

            try:
                await hit_limit(self.redis, "chat", f"tg:{chat_id}", s.questions_per_hour)
            except RateLimitExceeded as e:
                minutes = max(1, e.retry_after // 60)
                await self.tg.send(
                    chat_id,
                    f"Лимит демо: {e.limit} вопросов в час. Попробуйте через {minutes} мин.",
                )
                return

            typing = asyncio.create_task(self._keep_typing(chat_id))
            try:
                # Привязанный к админке чат видит и свои документы гостя; остальные — только
                # документы клиники
                _, reply, result = await ask(
                    session,
                    self.llm,
                    self.embedder,
                    self.redis,
                    conv,
                    question,
                    conv.visitor_id or "",
                    use_history,
                )
                # Клиент не спрашивал, а хотел записаться или позвать человека: в истории —
                # то, что бот сделал на самом деле
                if result.intent == "booking":
                    reply.text = BOOK_FROM_TEXT
                elif result.intent == "my_booking":
                    # «Я записан?» — ответ из заявок клиента, а не из документов
                    reply.text = booking_status_text(await _latest_booking(session, conv.id))
                elif result.intent == "cancel_booking":
                    reply.text = CANCEL_ASKED
                elif result.intent == "operator":
                    profile = await profile_for(session, conv.visitor_id)
                    reply.text, reply.reason = _operator_text(profile), "operator"
                if reply.answered is False:
                    conv.waiting_since = conv.waiting_since or now()
                    conv.attention_at = now()
                await session.commit()
            finally:
                typing.cancel()
            conv_id = conv.id

        if result.intent == "booking":
            await self._booking_start(chat, sender or {}, result.draft)
            return
        if result.intent == "my_booking":
            await self.tg.send(chat_id, escape(reply.text), MENU)
            return
        if result.intent == "cancel_booking":
            await self._ask_cancel(chat_id)
            return
        if result.intent == "operator":
            await self.tg.send(chat_id, reply.text, MENU)
            await notify_manager(
                self.tg,
                f"👤 <b>Клиент просит администратора</b>\n{_client(chat)}: «{escape(question)}»",
                conv_id,
            )
            return
        await self.tg.send(chat_id, reply_html(reply.text, reply.sources, title))
        if reply.answered is False:
            await notify_manager(
                self.tg,
                f"❓ <b>Бот не смог ответить</b>\n{_client(chat)}: «{escape(question)}»",
                conv_id,
            )

    async def _operator(self, chat: dict[str, Any]) -> None:
        text = _operator_text(await self._profile(chat["id"]))
        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            session.add_all(
                [
                    Message(conversation_id=conv.id, role="user", text=OPERATOR),
                    Message(
                        conversation_id=conv.id,
                        role="bot",
                        text=text,
                        reason="operator",
                        topic="other",
                    ),
                ]
            )
            conv.updated_at = now()
            conv.waiting_since = conv.waiting_since or now()
            conv.attention_at = now()
            await session.commit()
        await self.tg.send(chat["id"], text, MENU)
        await notify_manager(
            self.tg, f"👤 <b>Клиент просит администратора</b>\n{_client(chat)}", conv.id
        )

    # --- Кнопки под сообщениями ---

    async def _on_button(self, query: dict[str, Any]) -> None:
        data = query.get("data") or ""
        chat = (query.get("message") or {}).get("chat") or {}
        await self.tg.answer(query["id"])
        kind, _, key = data.partition(":")
        if chat.get("type") != "private":
            return
        if kind == "bk" and key in {"edit", "new", "keep"}:
            await self._booking_choice(query, chat, key)
            return
        if kind == "bk" and key in {"cancel", "stay"}:
            await self._cancel_choice(query, chat, key)
            return
        if kind != "price":
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

    async def _open_bookings(self, chat_id: int) -> list[Booking]:
        """Открытые заявки клиента, новые первыми: ждут звонка или подтверждены недавно."""
        since = now() - timedelta(days=CONFIRMED_DAYS)
        async with self.sessions() as session:
            rows = await session.scalars(
                select(Booking)
                .join(TelegramChat, TelegramChat.conversation_id == Booking.conversation_id)
                .where(
                    TelegramChat.chat_id == chat_id,
                    or_(
                        Booking.status == "new",
                        and_(Booking.status == "confirmed", Booking.created_at >= since),
                    ),
                )
                .order_by(Booking.created_at.desc())
            )
            return list(rows)

    async def _open_booking(self, chat_id: int) -> Booking | None:
        """Последняя открытая заявка клиента."""
        return next(iter(await self._open_bookings(chat_id)), None)

    async def _booking_start(
        self,
        chat: dict[str, Any],
        sender: dict[str, Any],
        draft: dict[str, str] | None = None,
        mode: str | None = None,
        edit_id: str | None = None,
    ) -> None:
        """Запись по шагам. draft — что клиент уже написал сам («Игорь, +7…, завтра в 12»):
        эти шаги пропускаются, бот спрашивает только недостающее.

        Если у клиента уже есть открытая заявка, бот сначала спрашивает, что с ней сделать.
        mode — ответ: edit (изменить или перенести её) или new (записать ещё одного)."""
        chat_id = chat["id"]
        if mode is None:
            existing = await self._open_booking(chat_id)
            if existing is not None:
                choice = {
                    "step": "choose",
                    "draft": draft,
                    "booking_id": existing.id,
                    "status": existing.status,
                }
                text = (
                    f"{OPEN_BOOKING[existing.status]}\n\n{_booking_lines(existing)}\n\nЧто сделать?"
                )
                sent = await self.tg.send(
                    chat_id, text, choice_buttons(existing.status == "confirmed")
                )
                # id сообщения — чтобы убрать кнопки, если клиент займётся другим
                choice["message_id"] = sent.get("message_id")
                await booking.save_state(self.redis, chat_id, choice)
                return

        state, bad_phone = booking.from_draft(draft or {})
        intro = BOOK_INTRO
        if mode == "edit" and edit_id:
            async with self.sessions() as session:
                old = await session.get(Booking, edit_id)
            if old is not None:
                # Остальное берём из заявки, если клиент не написал нового. Если его сообщение
                # ничего в заявке не меняет, он, видимо, хочет перенести её — спросим время
                if not booking.changes(state, old):
                    state.pop("time", None)
                state = {"name": old.name, "phone": old.phone, "reason": old.reason} | state
                state["edit_id"] = old.id
                intro = BOOK_EDIT_INTRO
        state["via"] = "text" if draft is not None else "button"
        state["suggest"] = booking.valid_name(sender.get("first_name") or "")
        step = booking.next_step(state)
        if step is None:
            await self._booking_done(chat, state)
            return
        state["step"] = step
        await booking.save_state(self.redis, chat_id, state)

        known = _booking_lines_partial(state)
        if known:
            intro += f"\n\nУже записал:\n{known}"
        if bad_phone:
            intro += f"\n\nВ номере «{escape(bad_phone)}» не хватает цифр."
        await self._ask_step(chat_id, state, intro)

    async def _remove_buttons(self, chat_id: int, message_id: int | None) -> None:
        if not message_id:
            return
        try:
            await self.tg.call(
                "editMessageReplyMarkup",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup={"inline_keyboard": []},
            )
        except TelegramError as e:
            log.warning("Telegram: %s", e)

    async def _note(self, chat_id: int, text: str) -> None:
        """Что произошло с записью — строкой в истории диалога: её увидит администратор."""
        async with self.sessions() as session:
            row = await session.get(TelegramChat, chat_id)
            if row is None:
                return
            session.add(
                Message(
                    conversation_id=row.conversation_id,
                    role="bot",
                    text=text,
                    reason="booking",
                    topic="booking",
                )
            )
            conv = await session.get(Conversation, row.conversation_id)
            conv.updated_at = now()
            await session.commit()

    async def _note_kept(self, chat_id: int, state: dict[str, Any]) -> None:
        async with self.sessions() as session:
            b = await session.get(Booking, state.get("booking_id") or "")
        if b is not None:
            await self._note(chat_id, booking_summary(b, kept=True))

    async def _leave_choice(self, chat_id: int, state: dict[str, Any]) -> None:
        """Клиент не стал выбирать, что делать с прежней записью, — она остаётся как есть."""
        await booking.clear_state(self.redis, chat_id)
        await self._remove_buttons(chat_id, state.get("message_id"))
        if state.get("step") == "choose":
            await self._note_kept(chat_id, state)

    async def _ask_cancel(self, chat_id: int) -> None:
        """«Отменить запись?» с кнопками — по /cancel или по просьбе словами."""
        existing = await self._open_booking(chat_id)
        if existing is None:
            await self.tg.send(chat_id, NOTHING_TO_CANCEL, MENU)
            return
        sent = await self.tg.send(
            chat_id, f"Отменить запись?\n\n{_booking_lines(existing)}", CANCEL_BUTTONS
        )
        await booking.save_state(
            self.redis,
            chat_id,
            {
                "step": "confirm_cancel",
                "booking_id": existing.id,
                "status": existing.status,
                "message_id": sent.get("message_id"),
            },
        )

    async def _cancel_choice(self, query: dict[str, Any], chat: dict[str, Any], key: str) -> None:
        chat_id = chat["id"]
        state = await booking.get_state(self.redis, chat_id)
        if not state or state.get("step") != "confirm_cancel":
            return
        await booking.clear_state(self.redis, chat_id)
        await self._remove_buttons(chat_id, (query.get("message") or {}).get("message_id"))
        if key == "stay":
            await self.tg.send(chat_id, BOOK_KEPT.get(state.get("status"), BOOK_KEPT["new"]), MENU)
            return
        async with self.sessions() as session:
            b = await session.get(Booking, state["booking_id"])
            # Администратор мог отменить её раньше — тогда отменять уже нечего
            if b is None or b.status == "cancelled":
                await self.tg.send(chat_id, NOTHING_TO_CANCEL, MENU)
                return
            b.status = "cancelled"
            b.client_changed_at = now()
            await session.commit()
            conv_id = b.conversation_id
        await self._note(chat_id, booking_summary(b, cancelled=True))
        await self.tg.send(chat_id, BOOKING_CANCELLED_DONE, MENU)
        await notify_manager(
            self.tg,
            f"❌ <b>Клиент отменил запись</b>\n{_client(chat)}\n\n{_booking_lines(b)}",
            conv_id,
        )

    async def _booking_choice(self, query: dict[str, Any], chat: dict[str, Any], key: str) -> None:
        """Кнопки под «У вас уже есть заявка»: изменить её, записать ещё одного или оставить."""
        chat_id = chat["id"]
        state = await booking.get_state(self.redis, chat_id)
        if not state or state.get("step") != "choose":
            return
        # Убираем кнопки: второе нажатие не начнёт запись заново
        await self._remove_buttons(chat_id, (query.get("message") or {}).get("message_id"))
        if key == "keep":
            await booking.clear_state(self.redis, chat_id)
            await self._note_kept(chat_id, state)
            await self.tg.send(chat_id, BOOK_KEPT.get(state.get("status"), BOOK_KEPT["new"]), MENU)
            return
        await self._booking_start(
            chat, query.get("from") or {}, state.get("draft"), mode=key, edit_id=state["booking_id"]
        )

    async def _ask_step(
        self, chat_id: int, state: dict[str, Any], prefix: str = "", greet: bool = False
    ) -> None:
        step = state["step"]
        if step == "name":
            rows = [[state["suggest"]], [CANCEL]] if state.get("suggest") else [[CANCEL]]
            text, markup = "Как вас зовут?", keyboard(rows, placeholder="Ваше имя")
        elif step == "phone":
            text = (GREET.format(name=escape(state["name"])) if greet else "") + ASK_PHONE
            share = {"text": SHARE_PHONE, "request_contact": True}
            markup = keyboard([[share], [CANCEL]], placeholder="+7 900 123-45-67")
        elif step == "reason":
            text, markup = ASK_REASON, keyboard([[SKIP], [CANCEL]], placeholder="Что беспокоит")
        else:
            text = ASK_TIME.format(hours=(await self._profile(chat_id)).hours)
            markup = keyboard([*booking.time_buttons(), [CANCEL]], placeholder="Удобное время")
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
            state["name"] = name
        elif step == "phone":
            phone = booking.normalize_phone(contact["phone_number"] if contact else text)
            if phone is None and contact:
                phone = "+" + "".join(c for c in contact["phone_number"] if c.isdigit())
            if phone is None:
                await self.tg.send(chat_id, PHONE_INVALID)
                return
            state["phone"] = phone
        elif step == "reason":
            if len(text) > booking.MAX_REASON:
                await self.tg.send(chat_id, TOO_LONG)
                return
            state["reason"] = None if text == SKIP else text
        else:
            if len(text) > booking.MAX_TIME:
                await self.tg.send(chat_id, TOO_LONG)
                return
            state["time"] = text

        following = booking.next_step(state)
        if following is None:
            await self._booking_done(msg["chat"], state)
            return
        state["step"] = following
        await booking.save_state(self.redis, chat_id, state)
        await self._ask_step(chat_id, state, greet=step == "name")

    async def _booking_done(self, chat: dict[str, Any], state: dict[str, Any]) -> None:
        fields = {
            "name": state["name"],
            "phone": state["phone"],
            "reason": state.get("reason"),
            "preferred_time": booking.pin_dates(state["time"])[: booking.MAX_TIME],
        }
        async with self.sessions() as session:
            b = await session.get(Booking, state["edit_id"]) if state.get("edit_id") else None
            # Пока клиент менял заявку, администратор мог её отменить — тогда это новая заявка
            edited = b is not None and b.status in {"new", "confirmed"}
            same_time = edited and booking.same_time(fields["preferred_time"], b.preferred_time)
            confirmed = edited and b.status == "confirmed"
            unchanged = same_time and all(
                getattr(b, k) == v for k, v in fields.items() if k != "preferred_time"
            )
        if unchanged:
            # Клиент ничего не поменял: статус и заявка прежние, менеджера не беспокоим
            await booking.clear_state(self.redis, chat["id"])
            await self._note(chat["id"], booking_summary(b, kept=True))
            await self.tg.send(chat["id"], NOTHING_CHANGED[b.status], MENU)
            return
        if not edited:
            # Тот же человек на то же время уже записан — вторую такую заявку не создаём
            twin = next(
                (
                    o
                    for o in await self._open_bookings(chat["id"])
                    if o.name.casefold() == fields["name"].casefold()
                    and booking.same_time(fields["preferred_time"], o.preferred_time)
                ),
                None,
            )
            if twin is not None:
                await booking.clear_state(self.redis, chat["id"])
                await self._note(chat["id"], booking_summary(twin, kept=True))
                await self.tg.send(chat["id"], ALREADY_BOOKED[twin.status], MENU)
                return
        async with self.sessions() as session:
            conv = await self._conversation(session, chat)
            if b is not None:
                b = await session.get(Booking, b.id)
            if edited:
                before = _booking_lines(b)
                for key, value in fields.items():
                    setattr(b, key, value)
                # Новое время администратор подтверждает заново; если время то же
                # (уточнили повод или телефон), подтверждённая запись остаётся подтверждённой
                if not same_time:
                    b.status = "new"
                b.client_changed_at = now()
            else:
                b = Booking(conversation_id=conv.id, **fields)
                session.add(b)
            # Начатая кнопкой запись — «📅 Записаться» в истории; начатая текстом — сообщение
            # клиента там уже есть
            if state.get("via") != "text":
                session.add(Message(conversation_id=conv.id, role="user", text=BOOK))
            session.add(
                Message(
                    conversation_id=conv.id,
                    role="bot",
                    text=booking_summary(b, edited),
                    reason="booking",
                    topic="booking",
                )
            )
            conv.updated_at = now()
            await session.commit()
        await booking.clear_state(self.redis, chat["id"])
        await self.tg.send(chat["id"], _book_done(b, edited), MENU)
        if edited:
            if confirmed and not same_time:
                title = "Клиент хочет перенести подтверждённую запись"
            elif confirmed:
                title = "Клиент изменил подтверждённую запись — время прежнее"
            else:
                title = "Заявка изменена"
            note = (
                f"✏️ <b>{title}</b>\n{_client(chat)}\n\n"
                f"<b>Было:</b>\n{before}\n\n<b>Стало:</b>\n{_booking_lines(b)}"
            )
        else:
            note = f"📅 <b>Новая заявка на запись</b>\n{_client(chat)}\n\n{_booking_lines(b)}"
        await notify_manager(self.tg, note, conv.id)
