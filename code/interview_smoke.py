import os


SMOKE_TEST_ENV_VAR = "INTERVIEW_SMOKE_TEST"
SMOKE_TEST_MODEL = "smoke-test-model"
INITIAL_SMOKE_REPLY = (
    "Hello! This is a smoke test interview. Please tell me in one sentence how the experience went."
)
MIXED_CLOSE_TRIGGER = "Trigger mixed close"
MIXED_CLOSE_REPLY = "Tell me more about the boundary you draw there. x7y8"
SMOKE_TEST_SUMMARY = "Smoke test summary generated locally."


def smoke_test_mode_enabled() -> bool:
    """Return whether the app is running in local UI smoke-test mode."""
    return os.environ.get(SMOKE_TEST_ENV_VAR, "").strip() == "1"


def next_smoke_reply(messages) -> str:
    """Return a deterministic assistant reply for browser smoke tests."""
    user_messages = [
        message
        for message in messages
        if message.get("role") == "user"
        and message.get("content") != "Please begin the interview following the provided instructions."
    ]
    if not user_messages:
        return INITIAL_SMOKE_REPLY
    if user_messages[0].get("content") == MIXED_CLOSE_TRIGGER:
        if len(user_messages) == 1:
            return MIXED_CLOSE_REPLY
        return "x7y8"
    return "x7y8"


def smoke_generate_summary(_: str) -> str:
    """Return a deterministic summary without calling an external model."""
    return SMOKE_TEST_SUMMARY


def smoke_noop(*args, **kwargs):
    """Discard side-effect calls during browser smoke tests."""
    del args, kwargs
    return None
