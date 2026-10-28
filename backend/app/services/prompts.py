"""Промпты и схемы ответов нейросети."""

from typing import Literal

from pydantic import BaseModel, Field

CLINIC = "Белая линия"

# Темы вопросов — для аналитики «топ тем». Модель выбирает тему сама, отдельный запрос не нужен
TOPICS = {
    "prices": "Цены",
    "booking": "Запись и приём",
    "doctors": "Врачи и график",
    "preparation": "Подготовка и уход",
    "warranty": "Гарантии",
    "payment": "Оплата и документы",
    "kids": "Дети",
    "other": "Другое",
}
Topic = Literal[
    "prices", "booking", "doctors", "preparation", "warranty", "payment", "kids", "other"
]


class CondensedQuestion(BaseModel):
    query: str = Field(description="Вопрос клиента, понятный без истории диалога")


class BotAnswer(BaseModel):
    answered: bool = Field(description="true — ответ есть во фрагментах; false — передать вопрос")
    answer: str = Field(description="Ответ клиенту; пустая строка, если answered=false")
    source_ids: list[int] = Field(description="Номера фрагментов, на которых основан ответ")
    topic: Topic


CONDENSE_SYSTEM = """Ты помогаешь чат-боту стоматологической клиники понять вопрос клиента.
Перепиши последний вопрос клиента так, чтобы он был понятен без истории диалога: подставь то,
о чём идёт речь («а это долго?» после разговора о коронках → «сколько времени делают коронку?»).
Ничего не добавляй от себя и не отвечай на вопрос. Если вопрос и так понятен без истории,
верни его без изменений. Ответ — JSON по схеме."""


ANSWER_SYSTEM = f"""Ты — администратор стоматологической клиники «{CLINIC}»
и отвечаешь клиентам в чате. Отвечай ТОЛЬКО по фрагментам документов клиники ниже.

Правила:
1. Бери факты только из фрагментов: цены, сроки, имена врачей, услуги, условия. Не добавляй
   ничего от себя и из общих знаний, не додумывай и не обобщай.
2. Если во фрагментах нет ответа на вопрос — answered=false и пустой answer. Так же, если
   спрашивают о том, чего в документах нет: другой услуге, враче, скидке, акции, другом
   бизнесе. Не пытайся ответить «примерно» и не предлагай похожее вместо спрошенного.
3. Если ответ есть — answered=true. Отвечай вежливо, на «вы», кратко и по делу: 1–4
   предложения или короткий список строками через «—». Цены пиши как во фрагментах,
   например «5 900 ₽». Если в вопросе несколько частей — ответь на каждую.
4. source_ids — номера фрагментов, из которых взят ответ.
5. Пиши обычным текстом без разметки: без звёздочек, решёток и таблиц. Не пиши, из какого
   документа ответ, — источник добавит система. Не здоровайся.
6. topic — тема вопроса.

Ответ — JSON по схеме."""


def _speaker(role: str) -> str:
    return {"user": "Клиент", "operator": "Администратор"}.get(role, "Бот")


def condense_prompt(history: list[tuple[str, str]], question: str) -> str:
    lines = ["История диалога:"]
    lines += [f"{_speaker(role)}: {text}" for role, text in history]
    lines += ["", f"Вопрос клиента: {question}"]
    return "\n".join(lines)


def answer_prompt(
    fragments: list[tuple[str, str]],
    history: list[tuple[str, str]],
    question: str,
    query: str,
) -> str:
    """fragments — пары (заголовок: документ и раздел, текст фрагмента)."""
    lines: list[str] = []
    if history:
        lines += ["История диалога:"]
        lines += [f"{_speaker(role)}: {text}" for role, text in history]
        lines += [""]
    lines += ["Фрагменты документов клиники:", ""]
    for i, (title, text) in enumerate(fragments, 1):
        lines += [f"[{i}] {title}", text, ""]
    lines += [f"Вопрос клиента: {question}"]
    if query != question:
        lines += [f"Смысл вопроса с учётом диалога: {query}"]
    return "\n".join(lines)
