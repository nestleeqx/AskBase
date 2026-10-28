from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Приводит строку подключения Neon/Heroku-вида к драйверу asyncpg.

    postgres://…?sslmode=require&channel_binding=require → postgresql+asyncpg://…?ssl=require
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"
    if not scheme.startswith("postgresql"):
        return url
    query = []
    for key, value in parse_qsl(parts.query):
        if key == "sslmode":
            query.append(("ssl", value))
        elif key != "channel_binding":
            query.append((key, value))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Интеграции Vercel (Neon, Upstash) называют переменные по-своему.
    # Прямое подключение без пулера предпочтительнее: asyncpg и pgbouncer плохо дружат.
    database_url: str = Field(
        default="postgresql+asyncpg://askbase:askbase@localhost:5434/askbase",
        validation_alias=AliasChoices(
            "DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING", "DATABASE_URL", "POSTGRES_URL"
        ),
    )
    redis_url: str = Field(
        default="redis://localhost:6380/0", validation_alias=AliasChoices("REDIS_URL", "KV_URL")
    )
    cors_origins: str = "http://localhost:3000"
    # Превью-деплои Vercel получают случайные адреса — их удобнее разрешить регуляркой
    cors_origin_regex: str | None = None
    # За прокси (Vercel, Render, nginx) реальный IP приходит в X-Forwarded-For
    trust_proxy: bool = True
    # Vercel выставляет VERCEL=1 во всех своих окружениях
    vercel: bool = False
    # Секрет, который Vercel Cron передаёт в Authorization: Bearer …
    cron_secret: str = ""
    # Адрес сайта: на нём лежит страница «Правила записи» из демо-базы.
    # Пусто — первый адрес из CORS_ORIGINS
    site_url: str = ""

    # Эмбеддинги — «смысл» фрагментов для поиска. openai — любой OpenAI-совместимый API,
    # yandex — Yandex Foundation Models (данные не покидают РФ),
    # mock — хеширование слов без внешнего API: для тестов и запуска без ключей.
    # Не задан — openai, если есть OPENAI_API_KEY, иначе mock
    embedding_provider: Literal["openai", "yandex", "mock"] | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    request_timeout: float = 30.0

    # Поиск: сколько фрагментов отдавать модели
    search_top_k: int = 6

    # Защита бюджета публичного демо
    max_question_chars: int = 500
    searches_per_hour: int = 60
    uploads_per_hour: int = 10
    # Свои документы гостя: сколько, какого размера; удаляются через сутки
    guest_docs_limit: int = 3
    max_upload_mb: float = 2.0
    max_pdf_pages: int = 20
    max_doc_chars: int = 50_000
    guest_docs_ttl_hours: int = 24
    cache_ttl_seconds: int = 7 * 24 * 3600

    # Загрузка страниц по ссылке: адреса локальной сети запрещены на проде,
    # но нужны при разработке. По умолчанию разрешены везде, кроме Vercel
    allow_private_urls: bool | None = None

    @field_validator("database_url")
    @classmethod
    def _normalize_db(cls, v: str) -> str:
        return normalize_database_url(v)

    @model_validator(mode="after")
    def _defaults(self) -> "Settings":
        if self.embedding_provider is None:
            self.embedding_provider = "openai" if self.openai_api_key else "mock"
        if self.allow_private_urls is None:
            self.allow_private_urls = not self.vercel
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def public_site_url(self) -> str:
        url = self.site_url or next(iter(self.cors_origin_list), "http://localhost:3000")
        return url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
