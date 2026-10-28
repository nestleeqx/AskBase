import json
import logging

import httpx
from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider, LLMRequestRejected, strict_schema
from app.llm.http import post_with_retry

log = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI Chat Completions. Подходит для OpenAI, OpenRouter, DeepSeek, vLLM, Ollama."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        json_mode: str = "json_schema",
        temperature: float = 0.4,
        reasoning_effort: str = "",
        timeout: float = 60.0,
    ):
        if not api_key:
            raise LLMError("Не задан OPENAI_API_KEY")
        self.model = model
        self.json_mode = json_mode
        # Необязательные параметры: модели серии GPT-5 и o-серии принимают не все из них.
        # Отклонённый параметр убираем и больше не отправляем.
        self._optional: dict[str, object] = {"temperature": temperature}
        if reasoning_effort:
            self._optional["reasoning_effort"] = reasoning_effort
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        if self.json_mode == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": strict_schema(schema),
                    "strict": True,
                },
            }
        else:
            # Без нативной поддержки схем передаём её в промпте
            system += "\n\nJSON Schema ответа:\n" + json.dumps(
                schema.model_json_schema(), ensure_ascii=False
            )
            response_format = {"type": "json_object"}

        payload = {
            "model": self.model,
            "response_format": response_format,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        while True:
            # Копия: параллельный запрос может убрать параметр, пока этот ждёт ответа
            optional = dict(self._optional)
            try:
                data = await post_with_retry(
                    self._client, self._url, headers=self._headers, json={**payload, **optional}
                )
                break
            except LLMRequestRejected as e:
                rejected = _rejected_param(e, optional)
                if rejected is None:
                    raise
                log.warning("Модель %s не принимает %s — отправляем без него", self.model, rejected)
                self._optional.pop(rejected, None)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(f"Неожиданный ответ API: {str(data)[:300]}") from e

    async def aclose(self) -> None:
        await self._client.aclose()


def _rejected_param(error: LLMRequestRejected, sent: dict[str, object]) -> str | None:
    """Какой из необязательных параметров API отклонил, если дело в нём."""
    if error.status != 400:
        return None
    try:
        param = json.loads(error.body)["error"].get("param") or ""
    except (ValueError, KeyError, AttributeError, TypeError):
        param = ""
    for name in sent:
        if name == param or name in error.body:
            return name
    return None
