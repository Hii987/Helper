import asyncio

import httpx
import pytest

from app import llm, prompts


def _resp(status, body=None, headers=None):
    return httpx.Response(status, json=body or {}, headers=headers or {}, request=httpx.Request("POST", llm.GROQ_URL))


OK = {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"total_tokens": 42}}


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "abc123")
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    return sleeps


def test_retries_after_rate_limit(monkeypatch, fast):
    responses = [_resp(429, {"message": "Requests rate limit exceeded"}), _resp(429), _resp(200, OK)]
    sent = []

    async def fake_post(payload, headers):
        sent.append(payload)
        return responses.pop(0)

    monkeypatch.setattr(llm, "_post", fake_post)
    message = asyncio.run(llm.complete([{"role": "user", "content": "x"}]))
    assert message["content"] == "ok"
    assert message["usage"]["total_tokens"] == 42
    assert len(sent) == 3
    assert fast == [2, 5]
    assert sent[0]["max_tokens"] == llm.MAX_OUTPUT_TOKENS


def test_gives_up_with_clear_message(monkeypatch, fast):
    async def fake_post(payload, headers):
        return _resp(429, {"message": "Requests rate limit exceeded"}, {"retry-after": "1"})

    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(llm.LLMError) as exc:
        asyncio.run(llm.complete([{"role": "user", "content": "x"}]))
    assert "Requests rate limit exceeded" in str(exc.value)
    assert fast == [1, 1, 1]


def test_profile_and_history_are_truncated():
    profile = {"cv": "x" * 10000}
    history = [{"role": "user", "content": str(i)} for i in range(30)]
    messages = prompts.chat_messages(profile, history)
    assert len(messages[0]["content"]) < prompts.MAX_PROFILE_FIELD + 1000
    assert len(messages) == 1 + prompts.MAX_HISTORY
    assert messages[-1]["content"] == "29"
