from app.config import Settings
from app.embeddings.base import EmbeddingError, EmbeddingProvider


def create_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        from app.embeddings.openai_compat import OpenAIEmbeddings

        return OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_embedding_model,
            timeout=settings.request_timeout,
        )
    if settings.embedding_provider == "yandex":
        from app.embeddings.yandex import YandexEmbeddings

        return YandexEmbeddings(
            api_key=settings.yandex_api_key,
            folder_id=settings.yandex_folder_id,
            timeout=settings.request_timeout,
        )
    from app.embeddings.mock import MockEmbeddings

    return MockEmbeddings()


__all__ = ["EmbeddingError", "EmbeddingProvider", "create_embedder"]
