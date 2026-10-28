import asyncio

import httpx

from app.embeddings.base import EmbeddingError, EmbeddingProvider, post_json

EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
# Yandex принимает один текст за запрос — параллелим, но без лишнего напора на лимиты
PARALLEL = 8


class YandexEmbeddings(EmbeddingProvider):
    """Yandex Foundation Models: отдельные модели для документов и для вопросов."""

    name = "yandex"
    model = "text-search"

    def __init__(self, api_key: str, folder_id: str, timeout: float = 30.0):
        if not api_key or not folder_id:
            raise EmbeddingError("Не заданы YANDEX_API_KEY и YANDEX_FOLDER_ID")
        self._doc_uri = f"emb://{folder_id}/text-search-doc/latest"
        self._query_uri = f"emb://{folder_id}/text-search-query/latest"
        self._headers = {"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id}
        self._client = httpx.AsyncClient(timeout=timeout)
        self._limit = asyncio.Semaphore(PARALLEL)

    async def _embed(self, uri: str, text: str) -> list[float]:
        async with self._limit:
            data = await post_json(
                self._client,
                EMBEDDING_URL,
                headers=self._headers,
                json={"modelUri": uri, "text": text},
            )
        try:
            return [float(x) for x in data["embedding"]]
        except (KeyError, TypeError, ValueError) as e:
            raise EmbeddingError(f"Неожиданный ответ Yandex: {str(data)[:300]}") from e

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self._embed(self._doc_uri, t) for t in texts)))

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(self._query_uri, text)

    async def aclose(self) -> None:
        await self._client.aclose()
