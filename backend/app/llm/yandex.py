import httpx
from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider
from app.llm.http import post_with_retry

COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGPTProvider(LLMProvider):
    """YandexGPT через Foundation Models API — данные не покидают РФ."""

    name = "yandex"

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        model: str = "yandexgpt/latest",
        temperature: float = 0.4,
        timeout: float = 60.0,
    ):
        if not api_key or not folder_id:
            raise LLMError("Не заданы YANDEX_API_KEY и YANDEX_FOLDER_ID")
        self.model = model
        self.temperature = temperature
        self._model_uri = f"gpt://{folder_id}/{model}"
        self._headers = {"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        data = await post_with_retry(
            self._client,
            COMPLETION_URL,
            headers=self._headers,
            json={
                "modelUri": self._model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": self.temperature,
                    "maxTokens": "4000",
                },
                "jsonSchema": {"schema": schema.model_json_schema()},
                "messages": [
                    {"role": "system", "text": system},
                    {"role": "user", "text": user},
                ],
            },
        )
        try:
            return data["result"]["alternatives"][0]["message"]["text"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"Неожиданный ответ YandexGPT: {str(data)[:300]}") from e

    async def aclose(self) -> None:
        await self._client.aclose()
