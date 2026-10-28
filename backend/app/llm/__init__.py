from app.config import Settings
from app.llm.base import LLMError, LLMInvalidResponse, LLMProvider


def create_provider(settings: Settings) -> LLMProvider:
    provider = _create(settings)
    if provider.name != "mock":
        provider.hedge_after = settings.llm_hedge_seconds or None
    return provider


def _create(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        from app.llm.openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            json_mode=settings.openai_json_mode,
            temperature=settings.llm_temperature,
            reasoning_effort=settings.openai_reasoning_effort,
            timeout=settings.llm_timeout,
        )
    if settings.llm_provider == "yandex":
        from app.llm.yandex import YandexGPTProvider

        return YandexGPTProvider(
            api_key=settings.yandex_api_key,
            folder_id=settings.yandex_folder_id,
            model=settings.yandex_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )
    from app.llm.mock import MockProvider

    return MockProvider()


__all__ = ["LLMError", "LLMInvalidResponse", "LLMProvider", "create_provider"]
