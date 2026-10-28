"""Демо-диалоги для раздела «Диалоги»: вымышленные клиенты пишут боту, бот отвечает по-настоящему.

    uv run python scripts/build_demo_dialogs.py

Вопросы клиентов, ответы администратора и заявки на запись заданы ниже, а ответы бота
получаются тем же конвейером, что в Telegram, — настоящей моделью (нужен ключ в .env и база
с проиндексированной демо-базой). Результат — app/seed/demo-dialogs.json: при старте API
диалоги из него попадают в базу, а время сообщений отсчитывается от момента запуска.
"""

import asyncio
import json
import sys
from pathlib import Path

import fakeredis
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.llm import create_provider  # noqa: E402
from app.models import Booking, Document  # noqa: E402
from app.services.answer import answer_question  # noqa: E402
from app.services.bot import BOOK, OPERATOR, _operator_text, booking_summary  # noqa: E402
from app.services.demo_dialogs import DEMO_FILE, VERSION  # noqa: E402
from app.services.dialogs import trace_of  # noqa: E402
from app.services.seed import ensure_seed  # noqa: E402

# Шаги: ("q", вопрос) — клиент спрашивает бота; ("admin", текст) — отвечает администратор;
# ("say", текст) — клиент пишет, пока отвечает администратор (бот молчит);
# ("operator",) — клиент нажал «Связаться с администратором»; ("book", заявка) — записался.
# Число перед шагом — пауза в минутах от предыдущего.
SCENARIOS = [
    {
        "key": "marina",
        "title": "Марина Королёва",
        "username": "marina_kor",
        "hours_ago": 140,
        "steps": [
            (0, "q", "Здравствуйте! Сколько стоит имплант под ключ?"),
            (1, "q", "А кто у вас ставит импланты?"),
            (2, "q", "Как подготовиться к имплантации?"),
            (
                3,
                "book",
                {
                    "name": "Марина",
                    "phone": "+7 (912) 345-67-80",
                    "reason": "консультация по имплантации",
                    "preferred_time": "в четверг после 18:00",
                    "status": "confirmed",
                },
            ),
        ],
    },
    {
        "key": "dmitry",
        "title": "Дмитрий Орлов",
        "username": None,
        "hours_ago": 112,
        "steps": [
            (0, "q", "Можно оплатить лечение в рассрочку?"),
            (1, "q", "А полис ДМС принимаете?"),
            (2, "q", "Скидки пенсионерам есть? Для мамы спрашиваю"),
        ],
    },
    {
        "key": "olga",
        "title": "Ольга Смирнова",
        "username": "olga_smirnova",
        "hours_ago": 86,
        "steps": [
            (0, "q", "Со скольки лет вы принимаете детей?"),
            (1, "q", "Сколько стоит вылечить молочный зуб?"),
            (1, "q", "Что взять с собой на приём с ребёнком?"),
            (
                2,
                "book",
                {
                    "name": "Ольга",
                    "phone": "+7 (922) 101-22-33",
                    "reason": "сыну 5 лет, кариес молочного зуба",
                    "preferred_time": "в субботу утром",
                    "status": "new",
                },
            ),
        ],
    },
    {
        "key": "igor",
        "title": "Игорь Васильев",
        "username": "igor_v",
        "hours_ago": 64,
        "steps": [
            (0, "q", "Можно ли у вас лечить зубы под общим наркозом?"),
            (
                14,
                "admin",
                "Здравствуйте, Игорь! Под общим наркозом мы не лечим — только под местной "
                "анестезией. Для тревожных пациентов врач заранее подробно объясняет каждый этап. "
                "Если хотите, запишу на консультацию: познакомитесь с врачом без лечения.",
            ),
            (3, "say", "Да, давайте, лучше в будни вечером"),
            (
                2,
                "admin",
                "Записала вас к Волкову Артёму Павловичу в четверг на 19:00. "
                "Накануне напомним о визите.",
            ),
        ],
    },
    {
        "key": "sergey",
        "title": "Сергей Павлов",
        "username": "spavlov",
        "hours_ago": 30,
        "steps": [
            (0, "q", "Сколько стоит отбеливание ZOOM?"),
            (1, "q", "А кофе потом пить можно?"),
        ],
    },
    {
        "key": "vika",
        "title": "Виктория",
        "username": "vika_m",
        "hours_ago": 20,
        "steps": [
            (0, "q", "Вы работаете в воскресенье?"),
            (1, "q", "Где у вас можно припарковаться?"),
        ],
    },
    {
        "key": "anna",
        "title": "Анна Петрова",
        "username": "anna_p",
        "hours_ago": 3,
        "steps": [
            (0, "q", "Сильно болит зуб, можно сегодня попасть?"),
            (1, "operator"),
        ],
    },
    {
        "key": "pavel",
        "title": "Павел",
        "username": None,
        "hours_ago": 0.7,
        "steps": [
            (0, "q", "Делаете протезирование на 4 имплантах, All-on-4? Сколько стоит?"),
        ],
    },
]

VISITOR = "demo-dialogs-build"


async def run() -> list[dict]:
    settings = get_settings()
    llm = create_provider(settings)
    embedder = create_embedder(settings)
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    await init_db()
    await ensure_seed(SessionLocal, embedder, redis)
    print(f"Модель: {llm.name} / {llm.model}, эмбеддинги: {embedder.model_id}")

    dialogs = []
    async with SessionLocal() as session:
        seed_keys = {
            d.id: d.seed_key
            for d in await session.scalars(select(Document).where(Document.seed_key.is_not(None)))
        }
        for sc in SCENARIOS:
            print(f"\n{sc['title']}")
            messages: list[dict] = []
            bookings: list[dict] = []
            history: list[tuple[str, str]] = []
            minute = 0.0

            def add(role: str, text: str, at: float, messages=messages, history=history, **extra):
                messages.append({"role": role, "text": text, "minute": round(at, 2), **extra})
                history.append((role, text))

            for pause, kind, *arg in sc["steps"]:
                minute += pause
                if kind == "q":
                    question = arg[0]
                    add("user", question, minute)
                    r = await answer_question(
                        session,
                        llm,
                        embedder,
                        redis,
                        question,
                        history[:-1][-settings.history_messages :],
                        VISITOR,
                    )
                    trace = trace_of(r)
                    for hit in trace["hits"]:
                        hit["document"]["id"] = seed_keys[hit["document"]["id"]]
                    minute += r.total_ms / 60000
                    add(
                        "bot",
                        r.text,
                        minute,
                        answered=r.answered,
                        reason=r.reason,
                        topic=r.topic,
                        sources=[
                            {"id": seed_keys[s.id], "title": s.title, "kind": s.kind}
                            for s in r.sources
                        ],
                        trace=trace,
                        latency_ms=r.total_ms,
                    )
                    mark = "✓" if r.answered else "→ администратору"
                    print(f"  {question}\n    {mark} {r.text} ({r.total_ms} мс)")
                elif kind == "say":
                    add("user", arg[0], minute)
                elif kind == "admin":
                    add("operator", arg[0], minute)
                elif kind == "operator":
                    add("user", OPERATOR, minute)
                    add("bot", _operator_text(), minute + 0.02, reason="operator", topic="other")
                elif kind == "book":
                    b = arg[0]
                    add("user", BOOK, minute)
                    minute += 1.5
                    summary = booking_summary(
                        Booking(**{k: v for k, v in b.items() if k != "status"})
                    )
                    add("bot", summary, minute, reason="booking", topic="booking")
                    bookings.append({**b, "minute": round(minute, 2)})
            dialogs.append(
                {
                    "key": sc["key"],
                    "title": sc["title"],
                    "username": sc["username"],
                    "hours_ago": sc["hours_ago"],
                    "messages": messages,
                    "bookings": bookings,
                }
            )
    return dialogs


def main() -> None:
    dialogs = asyncio.run(run())
    DEMO_FILE.write_text(
        json.dumps({"version": VERSION, "dialogs": dialogs}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"\nСохранено: {DEMO_FILE}")


if __name__ == "__main__":
    main()
