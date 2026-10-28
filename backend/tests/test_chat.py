import json

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider
from app.services.prompts import BotAnswer, CondensedQuestion
from tests.conftest import OTHER


class ScriptedLLM(LLMProvider):
    """Модель, которая отвечает заготовками и запоминает промпты."""

    name = "scripted"
    model = "test"

    def __init__(self, answer: dict | None = None, query: str | None = None, fail=False):
        self.answer = answer
        self.query = query
        self.fail = fail
        self.prompts: list[tuple[str, str]] = []

    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        self.prompts.append((schema.__name__, user))
        if self.fail:
            raise LLMError("недоступна")
        if schema is CondensedQuestion:
            return json.dumps({"query": self.query})
        assert schema is BotAnswer
        return json.dumps(self.answer, ensure_ascii=False)


def use_llm(llm):
    from app.main import app

    app.state.llm = llm


async def chat(client, question, conversation_id=None, **kw):
    body = {"question": question}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return await client.post("/api/chat", json=body, **kw)


async def test_answer_with_source(client):
    llm = ScriptedLLM(
        {
            "answered": True,
            "answer": "Мельников Игорь Сергеевич.",
            "source_ids": [1],
            "topic": "doctors",
        }
    )
    use_llm(llm)
    resp = await chat(client, "Кто ставит имплантаты, Мельников?")
    assert resp.status_code == 200
    body = resp.json()
    bot = body["bot"]
    assert bot["answered"] is True
    assert bot["text"] == "Мельников Игорь Сергеевич."
    assert bot["sources"][0]["title"] == "Врачи и график работы"
    assert bot["topic_label"] == "Врачи и график"
    trace = bot["trace"]
    assert trace["reason"] == "answered" and len(trace["hits"]) == 6
    assert trace["hits"][0]["used"] is True and not any(h["used"] for h in trace["hits"][1:])
    # Фрагменты переданы модели с номерами, вопрос — последней строкой
    name, prompt = llm.prompts[-1]
    assert name == "BotAnswer" and "[1] Врачи и график работы" in prompt
    assert prompt.rstrip().endswith("Вопрос клиента: Кто ставит имплантаты, Мельников?")


async def test_model_refusal_hands_off(client):
    use_llm(ScriptedLLM({"answered": False, "answer": "", "source_ids": [], "topic": "other"}))
    bot = (await chat(client, "Есть ли скидка для студентов?")).json()["bot"]
    assert bot["answered"] is False
    assert bot["text"] == "Уточню у администратора и вернусь с ответом."
    assert bot["trace"]["reason"] == "not_in_docs"
    assert bot["sources"] == []


async def test_answer_without_valid_sources_is_not_trusted(client):
    use_llm(
        ScriptedLLM({"answered": True, "answer": "Да, 20%.", "source_ids": [9], "topic": "prices"})
    )
    bot = (await chat(client, "Скидка студентам по прайсу есть?")).json()["bot"]
    assert bot["answered"] is False
    assert bot["trace"]["reason"] == "no_sources"


async def test_nothing_close_skips_model(client, monkeypatch):
    from app.config import get_settings

    llm = ScriptedLLM({"answered": True, "answer": "x", "source_ids": [1], "topic": "other"})
    use_llm(llm)
    monkeypatch.setattr(get_settings(), "answer_min_similarity", 0.99)
    bot = (await chat(client, "qwerty zxcvb")).json()["bot"]
    assert bot["answered"] is False and bot["trace"]["reason"] == "no_match"
    assert llm.prompts == []


async def test_follow_up_uses_history(client):
    first = ScriptedLLM(
        {
            "answered": True,
            "answer": "Да, ставим виниры E.max.",
            "source_ids": [1],
            "topic": "prices",
        }
    )
    use_llm(first)
    conv = (await chat(client, "Делаете керамические виниры?")).json()["conversation_id"]

    second = ScriptedLLM(
        {"answered": True, "answer": "32 000 ₽ за винир.", "source_ids": [1], "topic": "prices"},
        query="Сколько стоит керамический винир E.max?",
    )
    use_llm(second)
    bot = (await chat(client, "А сколько стоит?", conv)).json()["bot"]
    assert bot["trace"]["query"] == "Сколько стоит керамический винир E.max?"
    condense, answer = second.prompts
    assert condense[0] == "CondensedQuestion"
    assert "Клиент: Делаете керамические виниры?" in condense[1]
    assert "Бот: Да, ставим виниры E.max." in condense[1]
    assert "Смысл вопроса с учётом диалога: Сколько стоит керамический винир E.max?" in answer[1]
    # Нашёлся фрагмент прайса с винирами — по уточнённому вопросу
    assert any("винир" in h["text"].lower() for h in bot["trace"]["hits"][:3])

    messages = (await client.get(f"/api/chat/{conv}")).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "bot", "user", "bot"]


async def test_llm_failure_hands_off_politely(client):
    use_llm(ScriptedLLM(fail=True))
    resp = await chat(client, "Сколько стоит чистка?")
    assert resp.status_code == 200
    bot = resp.json()["bot"]
    assert bot["answered"] is False and bot["trace"]["reason"] == "error"
    assert "передал ваш вопрос администратору" in bot["text"]


async def test_same_question_is_cached(client):
    llm = ScriptedLLM(
        {"answered": True, "answer": "5 900 ₽.", "source_ids": [1], "topic": "prices"}
    )
    use_llm(llm)
    await chat(client, "Сколько стоит профессиональная гигиена?")
    bot = (await chat(client, "Сколько стоит профессиональная гигиена?")).json()["bot"]
    assert len(llm.prompts) == 1
    assert bot["trace"]["cached"] is True


async def test_conversation_is_private(client):
    use_llm(ScriptedLLM({"answered": False, "answer": "", "source_ids": [], "topic": "other"}))
    conv = (await chat(client, "Вопрос")).json()["conversation_id"]
    other = {"X-Visitor-Id": OTHER}
    assert (await client.get(f"/api/chat/{conv}", headers=other)).status_code == 404
    assert (await chat(client, "Ещё вопрос", conv, headers=other)).status_code == 404


async def test_question_validation_and_limit(client, monkeypatch):
    from app.config import get_settings

    use_llm(ScriptedLLM({"answered": False, "answer": "", "source_ids": [], "topic": "other"}))
    resp = await chat(client, "а" * 501)
    assert resp.status_code == 422 and "500 символов" in resp.json()["detail"]

    monkeypatch.setattr(get_settings(), "questions_per_hour", 1)
    assert (await chat(client, "Первый")).status_code == 200
    resp = await chat(client, "Второй")
    assert resp.status_code == 429
    assert "вопросов в час" in resp.json()["detail"]


async def test_mock_llm_answers_from_first_fragment(client):
    from app.llm.mock import MockProvider

    use_llm(MockProvider())
    bot = (await chat(client, "Кто ставит имплантаты, Мельников?")).json()["bot"]
    assert bot["answered"] is True
    assert bot["sources"][0]["title"] == "Врачи и график работы"
