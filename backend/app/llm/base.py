import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Сбой провайдера: сеть, лимиты, неверный ключ."""


class LLMRequestRejected(LLMError):
    """API отклонил запрос (4xx, кроме лимитов): неверный ключ, модель или параметр."""

    def __init__(self, status: int, body: str):
        super().__init__(f"Ошибка API нейросети {status}: {body[:300]}")
        self.status = status
        self.body = body


class LLMInvalidResponse(LLMError):
    """Модель ответила, но JSON не прошёл валидацию по схеме."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def extract_json(raw: str) -> Any:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema в строгом виде: все поля обязательны, лишние запрещены."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            # Служебные ключи default и title убираем, а поля модели внутри properties —
            # нет: у карточки есть своё поле title
            node = {
                k: ({name: walk(p) for name, p in v.items()} if k == "properties" else walk(v))
                for k, v in node.items()
                if k not in {"default", "title"}
            }
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema.model_json_schema())


class LLMProvider(ABC):
    """Единый интерфейс к нейросети. Провайдер выбирается переменной LLM_PROVIDER."""

    name: str
    model: str

    @abstractmethod
    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        """Вернуть сырой текст ответа модели, в котором должен быть JSON."""

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        raw = await self._complete(system, user, schema)
        try:
            return schema.model_validate(extract_json(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            raise LLMInvalidResponse(f"Ответ модели не соответствует схеме: {e}", raw) from e

    async def aclose(self) -> None:  # noqa: B027 — переопределяют провайдеры с HTTP-клиентом
        pass
