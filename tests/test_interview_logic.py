from types import SimpleNamespace

from interview_logic import (
    classify_assistant_reply,
    compose_system_prompt,
    extract_anthropic_text,
    extract_openai_stream_delta,
    filter_display_messages,
    find_closing_code,
    missing_query_params,
    normalize_query_value,
    resolve_query_params,
    serialize_transcript,
    should_accept_user_input,
    should_finalize_interview,
)


def test_normalize_query_value_handles_common_shapes():
    assert normalize_query_value(["midterm"], "Default") == "midterm"
    assert normalize_query_value(None, "Default") == "Default"
    assert normalize_query_value("direct", "Default") == "direct"


def test_resolve_query_params_prefers_live_values_and_falls_back_to_cached():
    current_params = {
        "name": "",
        "recipient_email": ["person@example.com"],
        "company": None,
    }
    cached_params = {
        "name": "Miros",
        "recipient_email": "old@example.com",
        "company": "ACME",
    }
    assert resolve_query_params(
        current_params,
        cached_params,
        ("name", "recipient_email", "company"),
    ) == {
        "name": "Miros",
        "recipient_email": "person@example.com",
        "company": "ACME",
    }


def test_missing_query_params_reports_only_empty_required_values():
    assert missing_query_params(
        {"name": "Miros", "recipient_email": ""},
        ("name", "recipient_email"),
    ) == ["recipient_email"]


def test_compose_system_prompt_includes_context_when_present():
    prompt = compose_system_prompt("Base prompt", "Earlier summary")
    assert "Earlier summary" in prompt
    assert prompt.endswith("Base prompt")


def test_extract_anthropic_text_ignores_non_text_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(text="Hello "),
            SimpleNamespace(other="ignored"),
            SimpleNamespace(text="world"),
        ]
    )
    assert extract_anthropic_text(response) == "Hello world"


def test_extract_openai_stream_delta_handles_missing_choices():
    assert extract_openai_stream_delta(SimpleNamespace(choices=[])) == ""
    assert (
        extract_openai_stream_delta(
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))])
        )
        == "Hi"
    )


def test_serialize_transcript_omits_non_chat_roles():
    messages = [
        {"role": "system", "content": "hidden"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Hi"},
    ]
    assert serialize_transcript(messages) == "assistant: Hello\nuser: Hi\n"


def test_find_closing_code_returns_first_matching_code():
    closing_messages = {"5j3k": "problem", "x7y8": "done"}
    assert find_closing_code("Please end x7y8 now", closing_messages) == "x7y8"
    assert find_closing_code("keep going", closing_messages) is None


def test_classify_assistant_reply_identifies_code_only_close():
    closing_messages = {"x7y8": "done"}
    parsed = classify_assistant_reply("  x7y8 \n", closing_messages)
    assert parsed.kind == "code_only_close"
    assert parsed.closing_code == "x7y8"
    assert parsed.visible_text == ""


def test_classify_assistant_reply_strips_mixed_content_close_code():
    closing_messages = {"x7y8": "done"}
    parsed = classify_assistant_reply("Tell me more about that. x7y8", closing_messages)
    assert parsed.kind == "mixed_content_with_code"
    assert parsed.closing_code == "x7y8"
    assert parsed.visible_text == "Tell me more about that."


def test_classify_assistant_reply_strips_mixed_content_close_code_with_trailing_whitespace():
    closing_messages = {"x7y8": "done"}
    parsed = classify_assistant_reply(
        "Tell me more about that. x7y8   \n",
        closing_messages,
    )
    assert parsed.kind == "mixed_content_with_code"
    assert parsed.closing_code == "x7y8"
    assert parsed.visible_text == "Tell me more about that."


def test_filter_display_messages_hides_system_and_code_only_messages():
    closing_messages = {"x7y8": "done"}
    messages = [
        {"role": "system", "content": "instructions"},
        {"role": "assistant", "content": "First question"},
        {"role": "assistant", "content": "x7y8"},
        {"role": "user", "content": "Answer"},
    ]
    assert filter_display_messages(messages, closing_messages) == [
        {"role": "assistant", "content": "First question"},
        {"role": "user", "content": "Answer"},
    ]


def test_filter_display_messages_sanitizes_mixed_content_code_messages():
    closing_messages = {"x7y8": "done"}
    messages = [
        {"role": "assistant", "content": "Tell me more about that. x7y8"},
        {"role": "user", "content": "Answer"},
    ]
    assert filter_display_messages(messages, closing_messages) == [
        {"role": "assistant", "content": "Tell me more about that."},
        {"role": "user", "content": "Answer"},
    ]


def test_state_helpers_cover_input_and_finalize_transitions():
    assert should_accept_user_input(True, False) is True
    assert should_accept_user_input(True, True) is False
    assert should_finalize_interview(False, False, False) is True
    assert should_finalize_interview(False, True, False) is False
    assert should_finalize_interview(False, False, True) is False
