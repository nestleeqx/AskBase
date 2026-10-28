import hashlib
import math
import re

from app.embeddings.base import EmbeddingProvider

DIMS = 512
_WORD = re.compile(r"[0-9a-zа-я]+")


def _bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % DIMS, 1.0 if value >> 63 else -1.0


def hashed_vector(text: str) -> list[float]:
    """Вектор из слов и их начал: близки тексты с общими словами, смысл не учитывается.

    Начало слова (5 букв) грубо заменяет основу: «удаление» и «удалить» совпадут.
    """
    vec = [0.0] * DIMS
    for word in _WORD.findall(text.lower().replace("ё", "е")):
        for feature, weight in ((word, 1.0), ("^" + word[:5], 1.5)):
            idx, sign = _bucket(feature)
            vec[idx] += sign * weight
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class MockEmbeddings(EmbeddingProvider):
    """Эмбеддинги без внешнего API — для тестов и запуска без ключей."""

    name = "mock"
    model = "hashed-words"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [hashed_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return hashed_vector(text)
