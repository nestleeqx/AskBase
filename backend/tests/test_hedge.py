"""Повторный запрос к модели, если первый задержался."""

import asyncio
import json

import pytest
from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider


class Reply(BaseModel):
    text: str


class SlowFirst(LLMProvider):
    """Первый запрос «зависает», остальные отвечают сразу."""

    name, model = "slow", "test"

    def __init__(self, first_delay: float, fail: bool = False):
        self.first_delay = first_delay
        self.fail = fail
        self.calls = 0

    async def _complete(self, system, user, schema):
        self.calls += 1
        n = self.calls
        if n == 1:
            await asyncio.sleep(self.first_delay)
            return json.dumps({"text": "первый"})
        if self.fail:
            raise LLMError("недоступна")
        return json.dumps({"text": "второй"})


async def test_second_request_wins_when_first_is_slow():
    llm = SlowFirst(first_delay=5)
    llm.hedge_after = 0.05
    started = asyncio.get_running_loop().time()
    reply = await llm.complete_json("s", "u", Reply)
    assert reply.text == "второй" and llm.calls == 2
    assert asyncio.get_running_loop().time() - started < 1


async def test_no_second_request_when_first_is_fast():
    llm = SlowFirst(first_delay=0)
    llm.hedge_after = 1
    assert (await llm.complete_json("s", "u", Reply)).text == "первый"
    assert llm.calls == 1


async def test_first_still_counts_if_second_fails():
    llm = SlowFirst(first_delay=0.2, fail=True)
    llm.hedge_after = 0.05
    assert (await llm.complete_json("s", "u", Reply)).text == "первый"


async def test_hedging_off():
    llm = SlowFirst(first_delay=0.1)
    assert llm.hedge_after is None
    assert (await llm.complete_json("s", "u", Reply)).text == "первый"
    assert llm.calls == 1


@pytest.mark.parametrize("provider", ["openai", "mock"])
def test_create_provider_sets_hedge(provider):
    from app.config import Settings
    from app.llm import create_provider

    settings = Settings(llm_provider=provider, openai_api_key="sk-test", llm_hedge_seconds=6)
    llm = create_provider(settings)
    assert llm.hedge_after == (6 if provider == "openai" else None)
