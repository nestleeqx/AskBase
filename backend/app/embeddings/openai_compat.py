import httpx

from app.embeddings.base import EmbeddingError, EmbeddingProvider, post_json

# Сколько текстов отправлять одним запросом: у OpenAI лимит 2048, но большие пачки дольше
# повторять при сбое
BATCH = 96


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI Embeddings API и совместимые с ним (OpenRouter, vLLM, Ollama)."""

    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 30.0):
        if not api_key:
            raise EmbeddingError("Не задан OPENAI_API_KEY")
        self.model = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        data = await post_json(
            self._client,
            self._url,
            headers=self._headers,
            json={"model": self.model, "input": texts},
        )
        try:
            items = sorted(data["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in items]
        except (KeyError, TypeError) as e:
            raise EmbeddingError(f"Неожиданный ответ API эмбеддингов: {str(data)[:300]}") from e

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            vectors += await self._embed(texts[start : start + BATCH])
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]

    async def aclose(self) -> None:
        await self._client.aclose()
