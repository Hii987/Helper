from app import prompts


def test_profile_and_history_are_truncated():
    profile = {"cv": "x" * 10000}
    history = [{"role": "user", "content": str(i)} for i in range(30)]
    messages = prompts.chat_messages(profile, history)
    assert len(messages[0]["content"]) < prompts.MAX_PROFILE_FIELD + 1000
    assert len(messages) == 1 + prompts.MAX_HISTORY
    assert messages[-1]["content"] == "29"


def test_json_mode_and_max_tokens(monkeypatch, fast):
    sent = []

    async def fake_post(payload, headers):
        sent.append(payload)
        return _resp(200, OK)

    monkeypatch.setattr(llm, "_post", fake_post)
    asyncio.run(llm.chat([{"role": "user", "content": "json"}], json_mode=True, max_tokens=3000))
    asyncio.run(llm.chat([{"role": "user", "content": "x"}]))
    assert sent[0]["response_format"] == {"type": "json_object"} and sent[0]["max_tokens"] == 3000
    assert "response_format" not in sent[1]


def test_degenerate_answer_is_retried(monkeypatch, fast):
    answers = ["## 1. Situation\n" + " " * 5000, "## 1. Situation\nOK"]

    async def fake_post(payload, headers):
        content = answers.pop(0)
        return _resp(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})

    monkeypatch.setattr(llm, "_post", fake_post)
    assert asyncio.run(llm.chat([{"role": "user", "content": "x"}])) == "## 1. Situation\nOK"


def test_degenerate_twice_gives_clear_error(monkeypatch, fast):
    async def fake_post(payload, headers):
        return _resp(200, {"choices": [{"message": {"role": "assistant", "content": " " * 500}}]})

    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(llm.LLMError):
        asyncio.run(llm.chat([{"role": "user", "content": "x"}]))
    assert not llm._degenerate("| --- | --- |\n" + "-" * 80)
