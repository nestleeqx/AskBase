import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, Message, TelegramChat
from app.services import bot as botmod
from app.services.answer import HANDOFF
from app.services.bot import Bot
from app.services.telegram import TelegramClient

CHAT = 777


class FakeTelegram(TelegramClient):
    """Вместо Telegram: запоминает вызовы и отвечает как Bot API."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._message_id = 100

    async def call(self, method, **params):
        self.calls.append((method, params))
        if method == "sendMessage":
            self._message_id += 1
            return {"message_id": self._message_id}
        if method == "sendDocument":
            return {"document": {"file_id": "FILE-1"}}
        return True

    async def _post(self, method, **kwargs):
        self.calls.append((method, {"upload": True, **kwargs.get("data", {})}))
        return {"document": {"file_id": "FILE-1"}}

    async def aclose(self):
        pass

    def of(self, method: str) -> list[dict]:
        return [params for name, params in self.calls if name == method]

    def texts(self) -> list[str]:
        return [p["text"] for p in self.of("sendMessage")]


@pytest.fixture
async def bot(client, redis):
    from app.main import app

    tg = FakeTelegram()
    yield Bot(SessionLocal, app.state.llm, app.state.embedder, redis, tg)


def message(text: str | None = None, chat_id: int = CHAT, chat_type="private", **extra) -> dict:
    chat = {"id": chat_id, "type": chat_type, "first_name": "Анна", "username": "anna"}
    msg = {"message_id": 1, "chat": chat, "from": {"id": chat_id, "first_name": "Анна"}}
    if text is not None:
        msg["text"] = text
    return {"update_id": 1, "message": msg | extra}


def button(data: str, chat_id: int = CHAT) -> dict:
    chat = {"id": chat_id, "type": "private", "first_name": "Анна"}
    return {
        "update_id": 2,
        "callback_query": {"id": "cb1", "data": data, "message": {"message_id": 5, "chat": chat}},
    }


async def say(bot: Bot, text: str | None = None, **extra) -> str:
    """Отправляет боту сообщение и возвращает последний ответ."""
    await bot.handle(message(text, **extra))
    return bot.tg.texts()[-1]


async def chat_messages(chat_id: int = CHAT) -> list[Message]:
    async with SessionLocal() as session:
        row = await session.get(TelegramChat, chat_id)
        if row is None:
            return []
        return list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == row.conversation_id)
                .order_by(Message.id)
            )
        )


@pytest.fixture(autouse=True)
async def clean_chats(database):
    yield
    async with SessionLocal() as session:
        for row in await session.scalars(select(TelegramChat)):
            from app.models import Conversation

            await session.delete(await session.get(Conversation, row.conversation_id))
        await session.commit()


async def test_start_shows_menu(bot):
    await bot.handle(message("/start"))
    sent = bot.tg.of("sendMessage")[-1]
    assert sent["text"] == botmod.GREETING
    buttons = [b["text"] for row in sent["reply_markup"]["keyboard"] for b in row]
    assert buttons == [botmod.PRICES, botmod.BOOK, botmod.OPERATOR]


async def test_question_answered_with_source(bot):
    reply = await say(bot, "Сколько стоит удаление зуба мудрости?")
    assert "<i>Источник: Прайс-лист</i>" in reply
    assert bot.tg.of("sendChatAction")[0]["action"] == "typing"
    msgs = await chat_messages()
    assert [m.role for m in msgs] == ["user", "bot"]
    assert msgs[1].answered is True
    async with SessionLocal() as session:
        row = await session.get(TelegramChat, CHAT)
        assert (row.title, row.username) == ("Анна", "anna")


async def test_out_of_base_question_is_handed_off(bot):
    reply = await say(bot, "Почините карбюратор у мотоцикла?")
    assert reply == HANDOFF
    assert (await chat_messages())[-1].answered is False


async def test_html_in_answer_is_escaped():
    html = botmod.reply_html("Цена <b>5 900 ₽</b> & скидки", [{"title": "Прайс-лист"}], "Чистка")
    assert html.startswith("<b>Чистка</b>\nЦена &lt;b&gt;5 900 ₽&lt;/b&gt; &amp; скидки")


async def test_prices_buttons_answer_without_history(bot):
    await say(bot, "Работаете в субботу?")
    await bot.handle(message(botmod.PRICES))
    markup = bot.tg.of("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    assert markup[-1][0]["callback_data"] == "price:pdf"

    await bot.handle(button("price:surgery"))
    assert bot.tg.of("answerCallbackQuery")[-1]["callback_query_id"] == "cb1"
    reply = bot.tg.texts()[-1]
    assert reply.startswith("<b>Удаление зубов</b>\n")
    # Вопрос с кнопки сохраняется в диалоге, как будто клиент написал его сам
    assert (await chat_messages())[-2].text == botmod.PRICE_TOPICS["surgery"][1]


async def test_price_list_pdf_uploaded_once(bot):
    await bot.handle(button("price:pdf"))
    await bot.handle(button("price:pdf"))
    uploads = [p for name, p in bot.tg.calls if name == "sendDocument" and p.get("upload")]
    by_id = [p for name, p in bot.tg.calls if name == "sendDocument" and not p.get("upload")]
    assert len(uploads) == 1
    assert by_id[0]["document"] == "FILE-1"


async def test_booking_flow(bot):
    first = await say(bot, botmod.BOOK)
    assert first == botmod.BOOK_START
    names = bot.tg.of("sendMessage")[-1]["reply_markup"]["keyboard"]
    assert names[0][0]["text"] == "Анна"

    assert "Оставьте телефон" in await say(bot, "Анна")
    share = bot.tg.of("sendMessage")[-1]["reply_markup"]["keyboard"][0][0]
    assert share["request_contact"] is True

    assert await say(bot, "завтра") == botmod.PHONE_INVALID
    contact = {"contact": {"phone_number": "79001234567", "user_id": CHAT}}
    assert "Что беспокоит" in await say(bot, None, **contact)
    assert "Когда вам удобно" in await say(bot, botmod.SKIP)
    done = await say(bot, "В субботу утром")

    assert "Заявка на запись принята" in done
    assert "Телефон: +7 (900) 123-45-67" in done
    assert "Повод" not in done
    async with SessionLocal() as session:
        b = await session.scalar(select(Booking))
        assert (b.name, b.phone, b.reason, b.preferred_time, b.status) == (
            "Анна",
            "+7 (900) 123-45-67",
            None,
            "В субботу утром",
            "new",
        )
    msgs = await chat_messages()
    assert msgs[-1].reason == "booking"
    assert msgs[-1].text.startswith("Заявка на запись: Анна, +7 (900) 123-45-67")

    # После записи бот снова отвечает на вопросы
    assert "Источник" in await say(bot, "Сколько стоит удаление зуба мудрости?")


async def test_booking_validates_and_cancels(bot):
    await say(bot, botmod.BOOK)
    assert await say(bot, "1") == botmod.NAME_INVALID
    await say(bot, "Пётр")
    assert "Что беспокоит" in await say(bot, "8 (912) 000 11 22")
    assert botmod.TEXT_ONLY in await say(bot, None)
    assert await say(bot, botmod.CANCEL) == botmod.BOOK_CANCELLED
    assert await say(bot, "/cancel") == botmod.NOTHING_TO_CANCEL
    async with SessionLocal() as session:
        assert await session.scalar(select(Booking).where(Booking.name == "Пётр")) is None


async def test_operator_request_logged(bot):
    reply = await say(bot, botmod.OPERATOR)
    assert "+7 (343) 200-18-18" in reply
    msgs = await chat_messages()
    assert [(m.role, m.reason) for m in msgs] == [("user", None), ("bot", "operator")]


async def test_non_text_and_groups(bot):
    assert await say(bot, None, sticker={"file_id": "x"}) == botmod.TEXT_ONLY
    await bot.handle(message("Сколько стоит чистка?", chat_id=-100, chat_type="group"))
    assert all(p["chat_id"] != -100 for p in bot.tg.of("sendMessage"))


async def test_limit_per_chat(bot):
    from app.config import get_settings

    settings = get_settings()
    old, settings.questions_per_hour = settings.questions_per_hour, 1
    try:
        await say(bot, "Сколько стоит чистка?")
        assert (await say(bot, "Сколько стоит отбеливание?")).startswith("Лимит демо: 1 вопросов")
    finally:
        settings.questions_per_hour = old


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("+7 900 123-45-67", "+7 (900) 123-45-67"),
        ("89001234567", "+7 (900) 123-45-67"),
        ("9001234567", "+7 (900) 123-45-67"),
        ("+49 151 2345 6789", "+4915123456789"),
        ("123", None),
        ("позвоните мне 89001234567", None),
    ],
)
def test_normalize_phone(raw, phone):
    from app.services.booking import normalize_phone

    assert normalize_phone(raw) == phone
