from datetime import date

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, Conversation, Message, TelegramChat
from app.services import booking
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
        # Демо-диалоги (отрицательные id) не трогаем — их создаёт запуск API
        for row in await session.scalars(select(TelegramChat).where(TelegramChat.chat_id > 0)):
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

    assert await say(bot, "Анна") == "Приятно познакомиться, Анна! " + botmod.ASK_PHONE
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
        b = await session.scalar(select(Booking).where(Booking.phone == "+7 (900) 123-45-67"))
        assert (b.name, b.phone, b.reason, b.preferred_time, b.status) == (
            "Анна",
            "+7 (900) 123-45-67",
            None,
            booking.pin_dates("В субботу утром"),
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
    assert "+7 (495) 200-18-18" in reply
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


def scripted_bot(bot: Bot, answer: dict) -> Bot:
    from tests.test_chat import ScriptedLLM

    return Bot(bot.sessions, ScriptedLLM(answer=answer), bot.embedder, bot.redis, bot.tg)


def intent(kind: str, **draft) -> dict:
    return {
        "intent": kind,
        "answered": False,
        "answer": "",
        "source_ids": [],
        "topic": "booking" if kind == "booking" else "other",
        "booking": {"name": "", "phone": "", "reason": "", "preferred_time": ""} | draft,
    }


async def test_booking_started_by_text(bot):
    assert await say(bot, "Хочу записаться к врачу") == botmod.BOOK_START
    msgs = await chat_messages()
    assert [(m.role, m.reason) for m in msgs] == [("user", None), ("bot", "booking_intent")]
    assert msgs[1].text == botmod.BOOK_FROM_TEXT and msgs[1].answered is None


async def test_booking_from_text_prefills_known_fields(bot):
    bot = scripted_bot(
        bot,
        intent(
            "booking",
            name="Игорь",
            phone="+7 945 48 41",
            reason="Отбелить зубы",
            preferred_time="завтра в 12:30",
        ),
    )
    reply = await say(bot, "Хочу записаться на отбеливание: Игорь, +7 945 48 41, завтра в 12:30")
    assert "Уже записал:\nИмя: Игорь\nПовод: Отбелить зубы\nУдобное время: завтра в 12:30" in reply
    assert "В номере «+7 945 48 41» не хватает цифр." in reply
    assert reply.endswith(f"не хватает цифр.\n\n{botmod.ASK_PHONE}")
    assert "Приятно познакомиться" not in reply

    # Остальное уже известно — после телефона заявка сразу готова
    done = await say(bot, "+7 945 480 41 00")
    # «Завтра» сохранено датой — через день в админке не будет висеть «завтра»
    pinned = booking.pin_dates("завтра в 12:30")
    assert "Заявка на запись принята" in done and f"Удобное время: {pinned}" in done
    assert "завтра" not in pinned
    msgs = await chat_messages()
    # Кнопку «Записаться» клиент не нажимал — в истории его собственное сообщение
    assert botmod.BOOK not in [m.text for m in msgs]
    assert msgs[-1].reason == "booking"


async def test_booking_from_text_with_everything_is_done_at_once(bot):
    draft = dict(name="Ольга", phone="89001234567", reason="", preferred_time="в субботу утром")
    bot = scripted_bot(bot, intent("booking", **draft))
    reply = await say(bot, "Запишите меня: Ольга, 89001234567, в субботу утром")
    # Повод не назван — спрашиваем только его
    assert "Что беспокоит" in reply and "Телефон: +7 (900) 123-45-67" in reply
    assert "Заявка на запись принята" in await say(bot, botmod.SKIP)


async def test_operator_requested_by_text(bot, redis):
    bot = scripted_bot(bot, intent("operator"))
    reply = await say(bot, "Позовите, пожалуйста, живого человека")
    assert "Передал ваш запрос администратору" in reply
    msgs = await chat_messages()
    assert msgs[-1].reason == "operator" and msgs[-1].answered is False


def test_from_draft_validates_fields():
    from app.services.booking import from_draft, next_step

    state, bad = from_draft(
        {"name": "1", "phone": "позвоните", "reason": " ", "preferred_time": ""}
    )
    assert state == {} and bad is None and next_step(state) == "name"
    state, bad = from_draft({"name": "Анна", "phone": "9001234567", "preferred_time": "утром"})
    assert state == {"name": "Анна", "phone": "+7 (900) 123-45-67", "time": "утром"} and bad is None
    assert next_step(state) == "reason"


async def book(bot: Bot, *answers: str) -> None:
    for text in [botmod.BOOK, *answers]:
        await bot.handle(message(text))


async def bookings_of_chat() -> list[Booking]:
    async with SessionLocal() as session:
        row = await session.get(TelegramChat, CHAT)
        return list(
            await session.scalars(
                select(Booking)
                .where(Booking.conversation_id == row.conversation_id)
                .order_by(Booking.created_at)
            )
        )


async def test_open_booking_asks_what_to_do(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    reply = await say(bot, botmod.BOOK)
    assert reply.startswith("У вас уже есть заявка на запись — администратор ещё не звонил")
    assert "Удобное время: Утром" in reply
    buttons = bot.tg.of("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    assert [row[0]["callback_data"] for row in buttons] == ["bk:edit", "bk:new", "bk:keep"]

    await bot.handle(button("bk:keep"))
    assert bot.tg.texts()[-1] == botmod.BOOK_KEPT["new"]
    # Кнопки под вопросом убраны — второе нажатие ничего не делает
    assert bot.tg.of("editMessageReplyMarkup")[-1]["reply_markup"] == {"inline_keyboard": []}
    sent = len(bot.tg.texts())
    await bot.handle(button("bk:edit"))
    assert len(bot.tg.texts()) == sent
    assert len(await bookings_of_chat()) == 1
    # В истории диалога администратор видит, чем кончилось
    assert (await chat_messages())[-1].text.startswith("Запись без изменений: Анна")


async def test_menu_button_leaves_booking_choice(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await say(bot, botmod.BOOK)
    choice_id = bot.tg._message_id
    # Вместо выбора клиент нажал «Цены» — бот показывает цены, а не «выберите вариант»
    assert await say(bot, botmod.PRICES) == botmod.PRICES_TEXT
    removed = bot.tg.of("editMessageReplyMarkup")[-1]
    assert removed["message_id"] == choice_id
    assert (await chat_messages())[-1].text.startswith("Запись без изменений: Анна")
    # Запись по шагам не продолжается: следующий текст — обычный вопрос
    assert "Источник" in await say(bot, "Сколько стоит удаление зуба мудрости?")


async def test_cancel_booking_is_noted(bot):
    await say(bot, "Хочу записаться к врачу")
    await say(bot, "Анна")
    assert await say(bot, botmod.CANCEL) == botmod.BOOK_CANCELLED
    assert (await chat_messages())[-1].text == botmod.BOOKING_CANCELLED_NOTE


async def test_smalltalk_is_not_handed_off(bot):
    reply = await say(bot, "Привет!")
    assert reply.startswith("Здравствуйте! Чем могу помочь?")
    await say(bot, "тест")
    msgs = await chat_messages()
    assert [m.reason for m in msgs if m.role == "bot"] == ["smalltalk", "smalltalk"]
    assert all(m.answered is None for m in msgs if m.role == "bot")
    # «Спасибо» после записи — не новая запись и не вопрос администратору
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    assert (await say(bot, "Спасибо большое")).startswith("Пожалуйста!")


def test_smalltalk_reply():
    from app.services.answer import smalltalk_reply

    assert smalltalk_reply("Добрый день!").startswith("Здравствуйте")
    assert smalltalk_reply("хорошо, спасибо").startswith("Пожалуйста")
    assert smalltalk_reply("всего доброго").startswith("Всего доброго")
    assert smalltalk_reply("ок").startswith("Хорошо")
    assert smalltalk_reply("привет, сколько стоит чистка?") is None
    assert smalltalk_reply("Здравствуйте, хочу записаться") is None


async def test_cancel_edit_keeps_booking(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await set_booking(status="confirmed")
    await say(bot, botmod.BOOK)
    await bot.handle(button("bk:edit"))
    # «Отмена» посреди правки отменяет правку, а не запись
    assert await say(bot, botmod.CANCEL) == botmod.BOOK_KEPT["confirmed"]
    bookings = await bookings_of_chat()
    assert (bookings[0].status, bookings[0].preferred_time) == ("confirmed", "Утром")
    assert (await chat_messages())[-1].text.startswith("Запись без изменений:")


async def test_edit_open_booking(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await say(bot, botmod.BOOK)
    await bot.handle(button("bk:edit"))
    reply = bot.tg.texts()[-1]
    # Имя, телефон и повод остаются — спрашиваем новое время
    assert reply.startswith(
        "Изменим вашу заявку.\n\nУже записал:\n"
        "Имя: Анна\nТелефон: +7 (900) 123-45-67\nПовод: Чистка"
    )
    assert "Когда вам удобно прийти" in reply
    done = await say(bot, "Вечером")
    assert done.startswith("<b>Заявка обновлена ✅</b>") and "Удобное время: Вечером" in done

    bookings = await bookings_of_chat()
    assert len(bookings) == 1
    assert (bookings[0].reason, bookings[0].preferred_time) == ("Чистка", "Вечером")
    assert (await chat_messages())[-1].text.startswith("Заявка изменена: Анна")


async def test_book_another_person(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await say(bot, botmod.BOOK)
    await bot.handle(button("bk:new"))
    assert bot.tg.texts()[-1] == botmod.BOOK_START
    for text in ["Миша", "+7 900 123-45-67", "Сыну 6 лет, кариес", "Утром"]:
        await bot.handle(message(text))
    assert "Заявка на запись принята" in bot.tg.texts()[-1]
    assert [b.name for b in await bookings_of_chat()] == ["Анна", "Миша"]


async def chat_conversation() -> Conversation:
    async with SessionLocal() as session:
        row = await session.get(TelegramChat, CHAT)
        return await session.get(Conversation, row.conversation_id)


async def test_only_human_requests_raise_attention(bot):
    # Клиент позвал администратора — админка подаст сигнал «ждёт администратора»
    await say(bot, botmod.OPERATOR)
    called = (await chat_conversation()).attention_at
    assert called is not None
    # Запись в том же диалоге — служебные сообщения, а не новый зов: сигнал будет только о заявке
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    conv = await chat_conversation()
    assert conv.attention_at == called and conv.updated_at > called


async def test_same_person_same_time_is_not_duplicated(bot):
    await book(bot, "Игорь", "+7 900 123-45-67", "Чистка", "на завтра на 12:30")
    await say(bot, botmod.BOOK)
    await bot.handle(button("bk:new"))
    # Тот же человек и то же время, хоть телефон и повод другие, — вторую заявку не создаём
    for text in ["игорь", "+7 900 122-31-12", "Пропустить", "завтра в 12:30"]:
        await bot.handle(message(text))
    assert bot.tg.texts()[-1] == botmod.ALREADY_BOOKED["new"]
    assert [b.name for b in await bookings_of_chat()] == ["Игорь"]


async def set_booking(**fields) -> None:
    async with SessionLocal() as session:
        b = await session.get(Booking, (await bookings_of_chat())[0].id)
        for key, value in fields.items():
            setattr(b, key, value)
        await session.commit()


async def test_move_confirmed_booking(bot, redis):
    from app.config import get_settings

    get_settings().manager_chat_id = 4242
    try:
        await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
        await set_booking(status="confirmed")
        reply = await say(bot, botmod.BOOK)
        assert reply.startswith("У вас уже есть запись — администратор её подтвердил")
        buttons = bot.tg.of("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
        assert buttons[0][0]["text"] == "✏️ Перенести или изменить"

        await bot.handle(button("bk:edit"))
        note = await say(bot, "В пятницу вечером")
        # Предпоследнее — ответ клиенту, последнее — уведомление менеджеру
        assert "Заявка обновлена" in bot.tg.texts()[-2]
        assert "Клиент хочет перенести подтверждённую запись" in note
        friday = booking.pin_dates("В пятницу вечером")
        assert "<b>Было:</b>" in note and f"Удобное время: {friday}" in note
        # Новое время подтверждает администратор — заявка снова ждёт звонка
        bookings = await bookings_of_chat()
        assert len(bookings) == 1
        assert (bookings[0].status, bookings[0].reason) == ("new", "Чистка")
    finally:
        get_settings().manager_chat_id = None


async def test_move_with_same_time_changes_nothing(bot):
    """Клиент нажал «Перенести», но в сообщении то же время — бот спрашивает новое,
    а если и оно прежнее, ничего не меняет и менеджеру не пишет."""
    from tests.test_chat import ScriptedLLM

    draft = dict(name="Анна", reason="Чистка", preferred_time="на утро")
    llm = ScriptedLLM(answer=intent("booking", **draft), query="запись на чистку")
    sbot = Bot(bot.sessions, llm, bot.embedder, bot.redis, bot.tg)
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утро")
    await set_booking(status="confirmed")
    await say(sbot, "Хочу записаться на чистку, Анна, на утро")
    await sbot.handle(button("bk:edit"))
    assert "Когда вам удобно прийти" in sbot.tg.texts()[-1]
    assert await say(sbot, "утро") == botmod.NOTHING_CHANGED["confirmed"]
    bookings = await bookings_of_chat()
    assert len(bookings) == 1 and bookings[0].status == "confirmed"


async def test_edit_confirmed_keeps_time_from_message(bot):
    """Сообщение меняет повод, а время в нём прежнее: бот не переспрашивает время,
    и запись остаётся подтверждённой — администратору подтверждать нечего."""
    from tests.test_chat import ScriptedLLM

    draft = dict(name="Анна", reason="Отбеливание", preferred_time="на утро")
    llm = ScriptedLLM(answer=intent("booking", **draft), query="запись")
    sbot = Bot(bot.sessions, llm, bot.embedder, bot.redis, bot.tg)
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утро")
    await set_booking(status="confirmed")
    await say(sbot, "Хочу на отбеливание, Анна, на утро")
    await sbot.handle(button("bk:edit"))
    done = sbot.tg.texts()[-1]
    assert done.startswith("<b>Заявка обновлена ✅</b>")
    assert "Повод: Отбеливание" in done and "Время записи прежнее" in done
    bookings = await bookings_of_chat()
    assert (bookings[0].status, bookings[0].reason) == ("confirmed", "Отбеливание")


def test_same_time():
    from app.services.booking import same_time

    assert same_time("на завтра на 12:30", "завтра в 12:30")
    assert not same_time("завтра в 15:00", "завтра в 12:30")
    assert not same_time("", "завтра")
    # Сохранённое датой «завтра» совпадает с новым «завтра»
    assert same_time("завтра в 12:30", booking.pin_dates("на завтра на 12:30"))


def test_time_buttons_name_the_day():
    thursday, saturday = date(2026, 10, 29), date(2026, 10, 31)
    assert booking.time_buttons(thursday)[0] == ["Завтра утром", "Завтра днём"]
    # Завтра воскресенье — клиника закрыта, предлагаем понедельник
    assert booking.time_buttons(saturday)[0][0] == "В понедельник утром"
    # Кнопка сохраняется датой
    assert booking.pin_dates("Завтра днём", thursday) == "30 октября днём"
    assert booking.pin_dates("В понедельник утром", saturday) == "В понедельник, 2 ноября утром"


def test_pin_dates():
    thursday = date(2026, 10, 29)
    assert booking.pin_dates("завтра в 12:30", thursday) == "30 октября в 12:30"
    assert booking.pin_dates("Сегодня вечером", thursday) == "29 октября вечером"
    assert booking.pin_dates("послезавтра", thursday) == "31 октября"
    assert booking.pin_dates("в субботу утром", thursday) == "в субботу, 31 октября утром"
    # Тот же день недели — следующая неделя; уже с датой — не трогаем
    assert booking.pin_dates("в четверг", thursday) == "в четверг, 5 ноября"
    assert booking.pin_dates("в субботу, 31 октября", thursday) == "в субботу, 31 октября"
    assert booking.pin_dates("после 18:00", thursday) == "после 18:00"


async def test_keep_confirmed_booking(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await set_booking(status="confirmed")
    await say(bot, botmod.BOOK)
    await bot.handle(button("bk:keep"))
    assert bot.tg.texts()[-1] == botmod.BOOK_KEPT["confirmed"]


async def test_old_or_cancelled_booking_does_not_ask(bot):
    from datetime import timedelta

    from app.models import now

    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    await set_booking(status="confirmed", created_at=now() - timedelta(days=15))
    assert await say(bot, botmod.BOOK) == botmod.BOOK_START
    await say(bot, botmod.CANCEL)
    await set_booking(status="cancelled", created_at=now())
    assert await say(bot, botmod.BOOK) == botmod.BOOK_START


async def test_my_booking_status(bot):
    # Заявок нет — бот так и говорит, а не ищет ответ в документах
    assert (await say(bot, "Я записан?")).startswith("Заявок на запись от вас пока нет")
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    reply = await say(bot, "Я записан?")
    assert reply.startswith("Ваша заявка на запись принята, администратор ещё не звонил")
    assert "Удобное время: Утром" in reply
    await set_booking(status="confirmed")
    assert (await say(bot, "Я записан?")).startswith("Да, вы записаны")
    msgs = await chat_messages()
    assert msgs[-1].reason == "my_booking" and msgs[-1].answered is None


async def test_cancel_confirmed_booking(bot, redis):
    from app.config import get_settings

    get_settings().manager_chat_id = 4242
    try:
        await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
        created = (await bookings_of_chat())[0].client_changed_at
        assert created is not None
        await set_booking(status="confirmed")
        reply = await say(bot, "/cancel")
        assert reply.startswith("Отменить запись?") and "Имя: Анна" in reply
        buttons = bot.tg.of("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
        assert [row[0]["callback_data"] for row in buttons] == ["bk:cancel", "bk:stay"]

        await bot.handle(button("bk:cancel"))
        # Клиенту — что запись отменена, менеджеру — уведомление
        assert bot.tg.texts()[-2] == botmod.BOOKING_CANCELLED_DONE
        assert "Клиент отменил запись" in bot.tg.texts()[-1]
        cancelled = (await bookings_of_chat())[0]
        assert cancelled.status == "cancelled"
        # Отмену сделал клиент — админка увидит новое действие и подаст сигнал
        assert cancelled.client_changed_at > created
        assert (await chat_messages())[-1].text.startswith("Клиент отменил запись: Анна")
        # Отменять больше нечего
        assert await say(bot, "/cancel") == botmod.NOTHING_TO_CANCEL
    finally:
        get_settings().manager_chat_id = None


async def test_cancel_by_text_and_stay(bot):
    await book(bot, "Анна", "+7 900 123-45-67", "Чистка", "Утром")
    assert (await say(bot, "Отмените мою запись, пожалуйста")).startswith("Отменить запись?")
    await bot.handle(button("bk:stay"))
    assert bot.tg.texts()[-1] == botmod.BOOK_KEPT["new"]
    assert (await bookings_of_chat())[0].status == "new"
