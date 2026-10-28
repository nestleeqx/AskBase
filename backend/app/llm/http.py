import asyncio
from typing import Any

import httpx

from app.llm.base import LLMError, LLMRequestRejected

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}


async def post_with_retry(
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
                raise LLMError(f"Нейросеть недоступна: {e}") from e
        else:
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code not in RETRY_STATUSES:
                raise LLMRequestRejected(resp.status_code, resp.text)
            if attempt == attempts:
                raise LLMError(f"Ошибка API нейросети {resp.status_code}: {resp.text[:300]}")
        await asyncio.sleep(delay)
        delay *= 2
    raise LLMError("Нейросеть не ответила")
