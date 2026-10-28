"""Шаблонные ответы без внешнего API — для тестов и запуска без ключей.

Отвечает текстом первого найденного фрагмента, если в нём есть слова вопроса, иначе
передаёт вопрос администратору. «Запишите…» — желание записаться, «позовите
администратора» — просьба о человеке. Разбирает промпт из app/services/prompts.py.
"""

import asyncio
import json
import re

from pydantic import BaseModel

from app.llm.base import LLMProvider

_WORD = re.compile(r"[0-9a-zа-яё]+")
_FRAGMENT = re.compile(r"^\[(\d+)\] .*?\n(.*?)(?=^\[\d+\] |^Вопрос клиента:)", re.S | re.M)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _WORD.findall(text.lower().replace("ё", "е")) if len(w) > 3}


def _line_after(prompt: str, label: str) -> str:
    """Текст последней строки с меткой: «Клиент:» — последняя реплика клиента в истории."""
    for line in reversed(prompt.splitlines()):
        if line.startswith(label):
            return line[len(label) :].strip()
    return ""


class MockProvider(LLMProvider):
    name = "mock"
    model = "first-fragment"

    def __init__(self, delay: float = 0.0):
        self.delay = delay

    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        if self.delay:
            await asyncio.sleep(self.delay)
        question = _line_after(user, "Вопрос клиента:")
        if schema.__name__ == "CondensedQuestion":
            previous = _line_after(user, "Клиент:")
            return json.dumps({"query": f"{previous} {question}".strip()}, ensure_ascii=False)

        lowered = question.lower()
        intent = (
            "cancel_booking"
            if re.search(r"отмен\w* (мою )?запис", lowered)
            else "my_booking"
            if re.search(r"я записан|моя запись|мою запись", lowered)
            else "booking"
            if re.search(r"запиш|записат", lowered)
            else "operator"
            if re.search(r"администратор|живого|человек", lowered)
            else "question"
        )
        draft = {"name": "", "phone": "", "reason": "", "preferred_time": ""}
        if intent != "question":
            return json.dumps(
                {
                    "intent": intent,
                    "answered": False,
                    "answer": "",
                    "source_ids": [],
                    "topic": "booking" if intent == "booking" else "other",
                    "booking": draft,
                },
                ensure_ascii=False,
            )

        fragments = {int(n): text.strip() for n, text in _FRAGMENT.findall(user)}
        first = fragments.get(1, "")
        answered = bool(first) and bool(_stems(question) & _stems(first))
        text = first.split("\n", 1)[-1][:300] if answered else ""
        return json.dumps(
            {
                "intent": "question",
                "answered": answered,
                "answer": text,
                "source_ids": [1] if answered else [],
                "topic": "other",
                "booking": draft,
            },
            ensure_ascii=False,
        )
