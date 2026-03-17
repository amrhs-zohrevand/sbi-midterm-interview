import interview_smoke


def test_smoke_test_mode_enabled_reads_env(monkeypatch):
    monkeypatch.setenv(interview_smoke.SMOKE_TEST_ENV_VAR, "1")
    assert interview_smoke.smoke_test_mode_enabled() is True

    monkeypatch.setenv(interview_smoke.SMOKE_TEST_ENV_VAR, "0")
    assert interview_smoke.smoke_test_mode_enabled() is False


def test_next_smoke_reply_starts_then_closes():
    first_reply = interview_smoke.next_smoke_reply(
        [{"role": "user", "content": "Please begin the interview following the provided instructions."}]
    )
    second_reply = interview_smoke.next_smoke_reply(
        [
            {"role": "assistant", "content": "intro"},
            {"role": "user", "content": "A normal reply"},
        ]
    )

    assert first_reply == interview_smoke.INITIAL_SMOKE_REPLY
    assert second_reply == "x7y8"


def test_next_smoke_reply_supports_mixed_content_close_regression_path():
    mixed_close_reply = interview_smoke.next_smoke_reply(
        [
            {"role": "assistant", "content": "intro"},
            {"role": "user", "content": interview_smoke.MIXED_CLOSE_TRIGGER},
        ]
    )
    final_close_reply = interview_smoke.next_smoke_reply(
        [
            {"role": "assistant", "content": "intro"},
            {"role": "user", "content": interview_smoke.MIXED_CLOSE_TRIGGER},
            {"role": "assistant", "content": mixed_close_reply},
            {"role": "user", "content": "The boundary is mostly about confidentiality."},
        ]
    )

    assert mixed_close_reply == interview_smoke.MIXED_CLOSE_REPLY
    assert final_close_reply == "x7y8"


def test_smoke_generate_summary_is_deterministic():
    assert (
        interview_smoke.smoke_generate_summary("anything")
        == interview_smoke.SMOKE_TEST_SUMMARY
    )
