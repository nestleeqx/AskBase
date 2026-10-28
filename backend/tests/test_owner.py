"""Вход владельца клиники и что ему доступно сверх гостя."""

import pytest

from app.db import SessionLocal
from app.models import Booking, Conversation, TelegramChat
from tests.conftest import OTHER

PASSWORD = "owner-test-pass"


async def owner_headers(client) -> dict:
    resp = await client.post("/api/auth/login", json={"password": PASSWORD})
    assert resp.status_code == 200
    return {"X-Owner-Token": resp.json()["token"]}


@pytest.fixture
async def other_chat(client):
    """Telegram-диалог другого посетителя с заявкой на запись."""
    async with SessionLocal() as session:
        conv = Conversation(channel="telegram", visitor_id=OTHER)
        session.add(conv)
        await session.flush()
        session.add(TelegramChat(chat_id=31337, conversation_id=conv.id, title="Чужой клиент"))
        await session.flush()
        b = Booking(
            conversation_id=conv.id, name="Олег", phone="+7 (900) 000-00-00", preferred_time="утром"
        )
        session.add(b)
        await session.commit()
        ids = conv.id, b.id
    yield ids
    async with SessionLocal() as session:
        await session.delete(await session.get(Conversation, ids[0]))
        await session.commit()


async def test_login(client):
    assert (await client.get("/api/auth")).json() == {"owner": False, "owner_enabled": True}
    resp = await client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401 and resp.json()["detail"] == "Неверный пароль."
    headers = await owner_headers(client)
    assert (await client.get("/api/auth", headers=headers)).json()["owner"] is True
    # Подделанный токен — обычный гость
    token = headers["X-Owner-Token"]
    forged = {"X-Owner-Token": token[:-1] + ("1" if token[-1] == "0" else "0")}
    assert (await client.get("/api/auth", headers=forged)).json()["owner"] is False


async def test_owner_sees_all_dialogs_and_bookings(client, other_chat):
    conv_id, booking_id = other_chat
    guest = (await client.get("/api/dialogs")).json()["dialogs"]
    assert conv_id not in [d["id"] for d in guest]
    headers = await owner_headers(client)
    owner = (await client.get("/api/dialogs", headers=headers)).json()["dialogs"]
    assert conv_id in [d["id"] for d in owner]
    assert (await client.get(f"/api/dialogs/{conv_id}", headers=headers)).status_code == 200

    resp = await client.patch(f"/api/bookings/{booking_id}", json={"status": "confirmed"})
    assert resp.status_code == 404
    resp = await client.patch(
        f"/api/bookings/{booking_id}", json={"status": "confirmed"}, headers=headers
    )
    assert resp.json()["status"] == "confirmed"
    # Демо-заявки не меняет и владелец
    demo = next(b for b in (await client.get("/api/bookings")).json()["bookings"] if b["demo"])
    resp = await client.patch(
        f"/api/bookings/{demo['id']}", json={"status": "new"}, headers=headers
    )
    assert resp.status_code == 403

    analytics = (await client.get("/api/analytics", headers=headers)).json()
    assert analytics["bookings"] >= 3


async def test_owner_settings_replace_own_guest_settings(client):
    """В этом же браузере раньше были свои гостевые настройки: после изменения общих
    владелец видит в своём подключённом Telegram общие, а не прежние гостевые."""
    guest_body = {
        "greeting": "Моё гостевое приветствие",
        "tone": "friendly",
        "phone": "+7 (900) 000-00-00",
        "hours": "круглосуточно",
    }
    assert (await client.put("/api/settings", json=guest_body)).json()["custom"] is True
    headers = await owner_headers(client)
    clinic_body = guest_body | {"greeting": "Общее приветствие клиники", "tone": "neutral"}
    await client.put("/api/settings", json=clinic_body, headers=headers)
    try:
        mine_as_guest = (await client.get("/api/settings")).json()
        assert (mine_as_guest["custom"], mine_as_guest["greeting"]) == (
            False,
            "Общее приветствие клиники",
        )
    finally:
        await client.delete("/api/settings", headers=headers)


async def test_owner_settings_apply_to_everyone(client):
    headers = await owner_headers(client)
    body = {
        "greeting": "Добро пожаловать в «Белую линию»!",
        "tone": "formal",
        "phone": "+7 (343) 111-11-11",
        "hours": "ежедневно 9:00–20:00",
    }
    data = (await client.put("/api/settings", json=body, headers=headers)).json()
    assert (data["scope"], data["custom"]) == ("clinic", True)
    try:
        guest = (await client.get("/api/settings", headers={"X-Visitor-Id": OTHER})).json()
        assert (guest["scope"], guest["custom"]) == ("guest", False)
        assert guest["greeting"] == body["greeting"] and guest["tone"] == "formal"
    finally:
        data = (await client.delete("/api/settings", headers=headers)).json()
    assert data["custom"] is False and data["tone"] == "neutral"


async def test_owner_uploads_to_clinic_base(client):
    headers = await owner_headers(client)
    files = {"file": ("akcii.txt", "АКЦИИ\nВ ноябре скидка 15% на чистку.".encode())}
    doc = (await client.post("/api/documents", files=files, headers=headers)).json()
    assert doc["status"] == "ready" and doc["own"] is True

    # Гости видят его как документ клиники и удалить не могут
    guest = (await client.get("/api/documents")).json()
    shared = next(d for d in guest["documents"] if d["id"] == doc["id"])
    assert shared["own"] is False
    assert guest["limits"]["guest_docs_left"] == guest["limits"]["guest_docs_limit"]
    assert (await client.delete(f"/api/documents/{doc['id']}")).status_code == 403

    limits = (await client.get("/api/documents", headers=headers)).json()["limits"]
    assert limits["owner"] is True
    seed = next(d for d in guest["documents"] if d["downloadable"])
    assert (await client.delete(f"/api/documents/{seed['id']}", headers=headers)).status_code == 403
    resp = await client.delete(f"/api/documents/{doc['id']}", headers=headers)
    assert resp.status_code == 204


async def test_owner_answer_goes_to_clinic_base(client):
    headers = await owner_headers(client)
    item = next(
        i
        for i in (await client.get("/api/unanswered", headers=headers)).json()["items"]
        if i["demo"]
    )
    body = {"question": item["question"], "answer": "All-on-4 делаем, цену назовёт имплантолог."}
    resp = await client.post(f"/api/unanswered/{item['id']}/answer", json=body, headers=headers)
    assert resp.status_code == 200
    try:
        # Ответ владельца — в общей базе: гость видит документ как документ клиники
        docs = (await client.get("/api/documents", headers={"X-Visitor-Id": OTHER})).json()
        answers = [d for d in docs["documents"] if d["title"] == "Ответы администратора"]
        assert len(answers) == 1 and answers[0]["own"] is False
    finally:
        owner_docs = (await client.get("/api/documents", headers=headers)).json()["documents"]
        doc = next(d for d in owner_docs if d["title"] == "Ответы администратора" and d["own"])
        await client.delete(f"/api/documents/{doc['id']}", headers=headers)
