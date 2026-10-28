import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Conversation, TelegramChat
from app.services import bot as botmod
from app.services.bot import Bot
from app.services.telegram import set_telegram
from tests.conftest import OTHER
from tests.test_bot import CHAT, FakeTelegram, message

MANAGER = 4242


@pytest.fixture
async def tg(client, redis):
    from app.main import app

    settings = get_settings()
    settings.telegram_bot_token = "123:test"
    fake = FakeTelegram()
    set_telegram(fake)
    fake.bot = Bot(SessionLocal, app.state.llm, app.state.embedder, redis, fake)
    yield fake
    settings.telegram_bot_token = ""
    settings.manager_chat_id = None
    set_telegram(None)
    async with SessionLocal() as session:
        for row in await session.scalars(select(TelegramChat).where(TelegramChat.chat_id > 0)):
            await session.delete(await session.get(Conversation, row.conversation_id))
        await session.commit()


async def _getme(fake: FakeTelegram):
    original = fake.call

    async def call(method, **params):
        if method == "getMe":
            fake.calls.append((method, params))
            return {"username": "white_line_test_bot"}
        return await original(method, **params)

    fake.call = call


async def link(client, tg) -> str:
    """Посетитель жмёт «Подключить Telegram» и «Старт» в боте — возвращает id своего диалога."""
    await _getme(tg)
    url = (await client.post("/api/telegram/link")).json()["url"]
    assert url.startswith("https://t.me/white_line_test_bot?start=")
    await tg.bot.handle(message(f"/start {url.split('start=')[1]}"))
    assert tg.texts()[-1].startswith(botmod.LINKED)
    own = [d for d in (await client.get("/api/dialogs")).json()["dialogs"] if not d["demo"]]
    assert len(own) == 1
    return own[0]["id"]


async def test_demo_dialogs_are_visible_and_readonly(client):
    data = (await client.get("/api/dialogs")).json()
    titles = [d["title"] for d in data["dialogs"]]
    assert len(titles) == 8 and all(d["demo"] for d in data["dialogs"])
    # Ждут человека: просьба позвать администратора и вопрос, на который бот не ответил
    assert data["waiting"] == 2
    assert titles[:2] == ["Павел", "Анна Петрова"] or set(titles[:2]) == {"Павел", "Анна Петрова"}

    found = (await client.get("/api/dialogs", params={"q": "рассрочк"})).json()["dialogs"]
    assert [d["title"] for d in found] == ["Дмитрий Орлов"]

    marina = next(d for d in data["dialogs"] if d["title"] == "Марина Королёва")
    detail = (await client.get(f"/api/dialogs/{marina['id']}")).json()
    assert detail["messages"][1]["sources"][0]["title"] == "Прайс-лист"
    assert detail["messages"][1]["trace"]["hits"]
    assert detail["messages"][-1]["reason"] == "booking"
    assert detail["bookings"][0]["status"] == "confirmed"

    resp = await client.post(f"/api/dialogs/{marina['id']}/reply", json={"text": "Здравствуйте"})
    assert resp.status_code == 403
    assert "пример диалога" in resp.json()["detail"]


async def test_telegram_status_without_token(client):
    assert (await client.get("/api/telegram")).json()["enabled"] is False
    assert (await client.post("/api/telegram/link")).status_code == 503


async def test_link_and_operator_reply(client, tg):
    await _getme(tg)
    status = (await client.get("/api/telegram")).json()
    assert status == {
        "enabled": True,
        "username": "white_line_test_bot",
        "linked": False,
        "manager": False,
    }
    conv_id = await link(client, tg)
    assert (await client.get("/api/telegram")).json()["linked"] is True
    # Чужой посетитель этот диалог не видит
    resp = await client.get(f"/api/dialogs/{conv_id}", headers={"X-Visitor-Id": OTHER})
    assert resp.status_code == 404

    await tg.bot.handle(message("Почините карбюратор у мотоцикла?"))
    dialog = (await client.get(f"/api/dialogs/{conv_id}")).json()
    assert dialog["waiting_since"] is not None

    resp = await client.post(f"/api/dialogs/{conv_id}/reply", json={"text": "Нет, <мы> не чиним"})
    assert resp.status_code == 200
    dialog = resp.json()
    assert dialog["waiting_since"] is None and dialog["operator_until"] is not None
    assert dialog["messages"][-1]["role"] == "operator"
    sent = tg.of("sendMessage")[-1]
    assert sent["chat_id"] == CHAT
    assert sent["text"] == "<b>Администратор клиники:</b>\nНет, &lt;мы&gt; не чиним"

    # Пока отвечает администратор, бот молчит: сообщение клиента ждёт человека
    before = len(tg.of("sendMessage"))
    await tg.bot.handle(message("Сколько стоит удаление зуба мудрости?"))
    assert len(tg.of("sendMessage")) == before
    dialog = (await client.get(f"/api/dialogs/{conv_id}")).json()
    assert dialog["messages"][-1]["role"] == "user" and dialog["waiting_since"] is not None

    dialog = (await client.post(f"/api/dialogs/{conv_id}/release")).json()
    assert dialog["operator_until"] is None
    assert tg.texts()[-1].startswith("Снова на связи бот клиники")
    await tg.bot.handle(message("Сколько стоит удаление зуба мудрости?"))
    assert "Источник: Прайс-лист" in tg.texts()[-1]


async def test_manager_notifications(client, tg):
    get_settings().manager_chat_id = MANAGER
    await tg.bot.handle(message("Почините карбюратор у мотоцикла?"))
    note = tg.of("sendMessage")[-1]
    assert note["chat_id"] == MANAGER
    assert note["text"].startswith(
        "🔔 <i>Для администратора клиники</i>\n❓ <b>Бот не смог ответить</b>\nАнна (@anna)"
    )
    # Ссылка на диалог — кнопкой (адрес сайта в тестах https)
    assert "/admin/dialogs?id=" in note["reply_markup"]["inline_keyboard"][0][0]["url"]

    await tg.bot.handle(message(botmod.OPERATOR))
    assert "\n👤 <b>Клиент просит администратора</b>" in tg.of("sendMessage")[-1]["text"]

    for text in [botmod.BOOK, "Анна", "+7 900 123-45-67", botmod.SKIP, "Вечером"]:
        await tg.bot.handle(message(text))
    note = tg.of("sendMessage")[-1]
    assert note["chat_id"] == MANAGER
    assert "Новая заявка на запись" in note["text"] and "Удобное время: Вечером" in note["text"]


async def test_bookings(client, tg):
    data = (await client.get("/api/bookings")).json()
    assert len(data["bookings"]) == 2 and data["new"] == 1
    demo = data["bookings"][0]
    resp = await client.patch(f"/api/bookings/{demo['id']}", json={"status": "cancelled"})
    assert resp.status_code == 403

    await link(client, tg)
    for text in [botmod.BOOK, "Анна", "+7 900 123-45-67", "Чистка", "Утром"]:
        await tg.bot.handle(message(text))
    data = (await client.get("/api/bookings")).json()
    own = data["bookings"][0]
    assert (own["demo"], own["client"], own["reason"], own["status"]) == (
        False,
        "Анна",
        "Чистка",
        "new",
    )
    assert data["new"] == 2

    resp = await client.patch(f"/api/bookings/{own['id']}", json={"status": "confirmed"})
    assert resp.json()["status"] == "confirmed"
    other = (await client.get("/api/bookings", headers={"X-Visitor-Id": OTHER})).json()
    assert len(other["bookings"]) == 2


async def test_webhook_requires_secret(client, tg):
    update = message("Сколько стоит удаление зуба мудрости?")
    resp = await client.post("/api/telegram/webhook", json=update)
    assert resp.status_code == 403
    secret = get_settings().telegram_webhook_secret
    resp = await client.post(
        "/api/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret}
    )
    assert resp.status_code == 200
    assert "Источник: Прайс-лист" in tg.texts()[-1]


async def test_webhook_set_on_vercel(client, tg):
    await _getme(tg)
    settings = get_settings()
    settings.vercel, settings.vercel_project_production_url = True, "askbase-api.vercel.app"
    try:
        await client.get("/api/telegram")
        await client.get("/api/telegram")
    finally:
        settings.vercel, settings.vercel_project_production_url = False, ""
    hooks = tg.of("setWebhook")
    # Один раз: дальше адрес берётся из кеша
    assert len(hooks) == 1
    assert hooks[0]["url"] == "https://askbase-api.vercel.app/api/telegram/webhook"
    assert hooks[0]["secret_token"] == settings.telegram_webhook_secret
