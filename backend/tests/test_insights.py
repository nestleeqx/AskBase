"""«Бот не смог ответить», настройки бота и аналитика."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Conversation, TelegramChat
from app.services.prompts import answer_system
from tests.conftest import OTHER
from tests.test_bot import CHAT, FakeTelegram, message
from tests.test_chat import chat


def demo_items(data: dict) -> list[dict]:
    # Тестовые чаты из других тестов тоже попадают в список — сверяемся по демо
    return [i for i in data["items"] if i["demo"]]


async def test_unanswered_demo_and_own(client):
    data = (await client.get("/api/unanswered")).json()
    # В демо бот не ответил Игорю (наркоз) и Павлу (All-on-4)
    demo = demo_items(data)
    assert len(demo) == 2
    questions = sorted(i["question"] for i in demo)
    assert questions[0].startswith("Делаете протезирование на 4 имплантах")
    assert questions[1].startswith("Можно ли у вас лечить зубы под общим наркозом")
    assert all(i["channel"] == "telegram" for i in demo)
    before = data["open"]

    await chat(client, "Почините карбюратор у мотоцикла?")
    data = (await client.get("/api/unanswered")).json()
    own = data["items"][0]
    assert (own["demo"], own["channel"], own["client"]) == (False, "test", "Тестовый чат")
    assert own["question"] == "Почините карбюратор у мотоцикла?"
    assert own["reason_label"] and data["open"] == before + 1

    # Чужой тестовый чат другому посетителю не виден
    other = (await client.get("/api/unanswered", headers={"X-Visitor-Id": OTHER})).json()
    assert own["id"] not in [i["id"] for i in other["items"]]


async def test_resolve_demo_question_only_for_me(client):
    item = demo_items((await client.get("/api/unanswered")).json())[0]
    resp = await client.post(f"/api/unanswered/{item['id']}/resolve", json={"resolved": True})
    assert resp.json()["resolved"] is True
    mine = (await client.get("/api/unanswered", params={"status": "all"})).json()
    assert [i["resolved"] for i in demo_items(mine)] == [True, False] or [
        i["resolved"] for i in demo_items(mine)
    ] == [False, True]
    other = (await client.get("/api/unanswered", headers={"X-Visitor-Id": OTHER})).json()
    assert len(demo_items(other)) == 2

    resp = await client.post(f"/api/unanswered/{item['id']}/resolve", json={"resolved": False})
    assert resp.json()["resolved"] is False


async def test_answer_goes_to_knowledge_base(client):
    await chat(client, "Почините карбюратор у мотоцикла?")
    item = (await client.get("/api/unanswered")).json()["items"][0]
    body = {"question": item["question"], "answer": "Карбюраторы мы не чиним — мы стоматология."}
    resp = await client.post(f"/api/unanswered/{item['id']}/answer", json=body)
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True and resp.json()["kb_answer"].startswith("Карбюраторы")

    docs = (await client.get("/api/documents")).json()
    answers = [d for d in docs["documents"] if d["title"] == "Ответы администратора"]
    assert len(answers) == 1 and answers[0]["status"] == "ready" and answers[0]["own"]
    # Документ с ответами не занимает место в лимите своих документов гостя
    assert docs["limits"]["guest_docs_left"] == docs["limits"]["guest_docs_limit"]

    # Теперь бот отвечает на этот вопрос сам — по ответу администратора
    reply = (await chat(client, "Почините карбюратор у мотоцикла?")).json()["bot"]
    assert reply["answered"] is True
    assert [s["title"] for s in reply["sources"]] == ["Ответы администратора"]


async def test_settings_per_visitor(client, redis):
    data = (await client.get("/api/settings")).json()
    assert data["custom"] is False and data["tone"] == "neutral"
    assert data["tones"]["friendly"] == "Дружелюбный"

    body = {
        "greeting": "Привет! Я бот «Белой линии», спрашивайте.",
        "tone": "friendly",
        "phone": "+7 (343) 000-00-00",
        "hours": "ежедневно 8:00–22:00",
    }
    data = (await client.put("/api/settings", json=body)).json()
    assert data["custom"] is True and data["greeting"].startswith("Привет!")
    other = (await client.get("/api/settings", headers={"X-Visitor-Id": OTHER})).json()
    assert other["custom"] is False

    # Бот в подключённом Telegram-чате гостя берёт его настройки
    from app.main import app
    from app.services.bot import Bot

    async with SessionLocal() as session:
        conv = Conversation(channel="telegram", visitor_id="test-visitor-0001")
        session.add(conv)
        await session.flush()
        session.add(TelegramChat(chat_id=CHAT, conversation_id=conv.id, title="Анна"))
        await session.commit()
    try:
        tg = FakeTelegram()
        bot = Bot(SessionLocal, app.state.llm, app.state.embedder, redis, tg)
        await bot.handle(message("/start"))
        assert tg.texts()[-1] == body["greeting"]
        await bot.handle(message("👤 Связаться с администратором"))
        assert "ежедневно 8:00–22:00" in tg.texts()[-1] and "+7 (343) 000-00-00" in tg.texts()[-1]
    finally:
        async with SessionLocal() as session:
            row = await session.scalar(select(TelegramChat).where(TelegramChat.chat_id == CHAT))
            await session.delete(await session.get(Conversation, row.conversation_id))
            await session.commit()

    data = (await client.delete("/api/settings")).json()
    assert data["custom"] is False


def test_tone_changes_prompt():
    assert answer_system("neutral") == answer_system("unknown")
    assert "дружелюбный" in answer_system("friendly")
    assert "Стиль ответа" not in answer_system("neutral")


async def test_analytics_on_demo(client):
    data = (await client.get("/api/analytics")).json()
    assert len(data["days"]) == 7
    assert (data["dialogs"], data["questions"], data["answered"]) == (8, 16, 14)
    assert (data["bookings"], data["operator_requests"], data["unanswered"]) == (2, 1, 2)
    assert round(data["answered_share"], 3) == round(14 / 16, 3)
    assert data["median_ms"] > 0
    labels = [t["label"] for t in data["topics"]]
    assert labels and "Цены" in labels
    assert sum(d["dialogs"] for d in data["days"]) >= 8
