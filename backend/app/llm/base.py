import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)


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
    # Через сколько секунд без ответа отправить второй такой же запрос. Иногда API отвечает
    # не за 2 секунды, а за 20–30; второй запрос в это время обычно возвращается быстро.
    # None — не дублировать (mock и тесты)
    hedge_after: float | None = None

    @abstractmethod
    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        """Вернуть сырой текст ответа модели, в котором должен быть JSON."""

    async def _hedged(self, system: str, user: str, schema: type[BaseModel]) -> str:
        """Первый успешный из двух запросов: второй уходит, если первый задержался.
        Первый не отменяется — если он всё же придёт раньше, берём его."""
        first = asyncio.create_task(self._complete(system, user, schema))
        if not self.hedge_after:
            return await first
        done, _ = await asyncio.wait({first}, timeout=self.hedge_after)
        if done:
            return first.result()
        log.info("Модель не ответила за %s с — отправляем повторный запрос", self.hedge_after)
        pending = {first, asyncio.create_task(self._complete(system, user, schema))}
        error: BaseException | None = None
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task.exception() is None:
                        return task.result()
                    error = task.exception()
            raise error  # оба запроса не удались
        finally:
            for task in pending:
                task.cancel()

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        raw = await self._hedged(system, user, schema)
        try:
            return schema.model_validate(extract_json(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            raise LLMInvalidResponse(f"Ответ модели не соответствует схеме: {e}", raw) from e

    async def aclose(self) -> None:  # noqa: B027 — переопределяют провайдеры с HTTP-клиентом
        pass
