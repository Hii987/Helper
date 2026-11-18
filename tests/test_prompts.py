from app import prompts


def test_profile_and_history_are_truncated():
    profile = {"cv": "x" * 10000}
    history = [{"role": "user", "content": str(i)} for i in range(30)]
    messages = prompts.chat_messages(profile, history)
    assert len(messages[0]["content"]) < prompts.MAX_PROFILE_FIELD + 1000
    assert len(messages) == 1 + prompts.MAX_HISTORY
    assert messages[-1]["content"] == "29"
