import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}


class EmbeddingError(Exception):
    """Не удалось посчитать эмбеддинги: сеть, лимиты, неверный ключ."""


class EmbeddingProvider(ABC):
    """Векторы смысла для текстов. Провайдер выбирается переменной EMBEDDING_PROVIDER.

    Документы и вопросы кодируются отдельно: у некоторых моделей (Yandex) для них разные версии.
    """

    name: str
    model: str

    @property
    def model_id(self) -> str:
        """Метка, по которой видно, какой моделью посчитан сохранённый вектор."""
        return f"{self.name}:{self.model}"

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...

    async def aclose(self) -> None:  # noqa: B027 — переопределяют провайдеры с HTTP-клиентом
        pass


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
    attempts: int = 3,
) -> dict[str, Any]:
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            resp = await client.post(url, json=json, headers=headers)
        except httpx.TransportError as e:
            if attempt == attempts:
                raise EmbeddingError(f"API эмбеддингов недоступен: {e}") from e
        else:
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code not in RETRY_STATUSES or attempt == attempts:
                raise EmbeddingError(
                    f"Ошибка API эмбеддингов {resp.status_code}: {resp.text[:300]}"
                )
        await asyncio.sleep(delay)
        delay *= 2
    raise EmbeddingError("API эмбеддингов не ответил")
