from types import SimpleNamespace

from interview_logic import (
    compose_system_prompt,
    extract_anthropic_text,
    filter_display_messages,
    find_closing_code,
    normalize_query_value,
    serialize_transcript,
    should_accept_user_input,
    should_finalize_interview,
)


def test_normalize_query_value_handles_common_shapes():
    assert normalize_query_value(["midterm"], "Default") == "midterm"
    assert normalize_query_value(None, "Default") == "Default"
    assert normalize_query_value("direct", "Default") == "direct"


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


def test_state_helpers_cover_input_and_finalize_transitions():
    assert should_accept_user_input(True, False) is True
    assert should_accept_user_input(True, True) is False
    assert should_finalize_interview(False, False, False) is True
    assert should_finalize_interview(False, True, False) is False
    assert should_finalize_interview(False, False, True) is False
