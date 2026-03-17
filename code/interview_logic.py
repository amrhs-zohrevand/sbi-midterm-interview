from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantReplyClassification:
    kind: str
    visible_text: str
    closing_code: str | None = None


def normalize_query_value(value, default="") -> str:
    """Normalize a Streamlit query-param value to a plain string."""
    if isinstance(value, list):
        value = value[0] if value else default
    if value is None:
        value = default
    return str(value)


def resolve_query_params(params, cached_params, keys):
    """Merge current query params with cached launch params, preferring live values."""
    cached_params = cached_params or {}
    return {
        key: normalize_query_value(params.get(key)) or normalize_query_value(cached_params.get(key))
        for key in keys
    }


def missing_query_params(params, required_keys):
    """Return the required query params that are still empty after normalization."""
    return [key for key in required_keys if not normalize_query_value(params.get(key))]


def compose_system_prompt(base_prompt: str, context_transcript: str | None = None) -> str:
    """Compose the system prompt from config plus optional prior context."""
    if not context_transcript:
        return base_prompt

    return (
        "Context Transcript Summary (provided as context for the interview):\n\n"
        f"{context_transcript}\n\n"
        f"{base_prompt}"
    )


def extract_anthropic_text(response) -> str:
    """Flatten Anthropic content blocks into plain text."""
    parts = []
    for block in getattr(response, "content", []):
        text = getattr(block, "text", "")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def extract_openai_stream_delta(chunk) -> str:
    """Return visible text from an OpenAI-compatible stream chunk."""
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""

    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""

    text = getattr(delta, "content", "") or ""
    if isinstance(text, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else ""
            for item in text
        )
    return text


def serialize_transcript(messages) -> str:
    """Serialize visible user/assistant messages for persistence."""
    return "".join(
        f"{message['role']}: {message['content']}\n"
        for message in messages
        if message["role"] in {"user", "assistant"}
    )


def find_closing_code(message_text: str, closing_messages) -> str | None:
    """Return the first configured closing code found in a message."""
    for code in closing_messages:
        if code in message_text:
            return code
    return None


def classify_assistant_reply(
    message_text: str, closing_messages
) -> AssistantReplyClassification:
    """Classify assistant text as a code-only close, mixed content, or normal text."""
    text = message_text or ""
    stripped_text = text.strip()

    for code in closing_messages:
        if stripped_text == code:
            return AssistantReplyClassification(
                kind="code_only_close",
                visible_text="",
                closing_code=code,
            )

    visible_text = text
    closing_code = None
    for code in closing_messages:
        if code in visible_text:
            closing_code = closing_code or code
            visible_text = visible_text.replace(code, "")

    if closing_code:
        return AssistantReplyClassification(
            kind="mixed_content_with_code",
            visible_text=visible_text.strip(),
            closing_code=closing_code,
        )

    return AssistantReplyClassification(
        kind="normal_text",
        visible_text=text,
        closing_code=None,
    )


def filter_display_messages(messages, closing_messages):
    """Return the subset of messages that should appear in the chat UI."""
    visible_messages = []
    for message in messages:
        if message["role"] == "system":
            continue
        if message["role"] != "assistant":
            visible_messages.append(message)
            continue

        parsed_reply = classify_assistant_reply(message["content"], closing_messages)
        if parsed_reply.kind == "code_only_close":
            continue

        if parsed_reply.kind == "mixed_content_with_code":
            visible_messages.append(
                {**message, "content": parsed_reply.visible_text}
            )
            continue

        visible_messages.append(message)
    return visible_messages


def should_accept_user_input(
    interview_active: bool, awaiting_email_confirmation: bool
) -> bool:
    """Return whether the chat input should still be active."""
    return interview_active and not awaiting_email_confirmation


def should_finalize_interview(
    interview_active: bool,
    awaiting_email_confirmation: bool,
    completion_saved: bool,
) -> bool:
    """Return whether the interview should enter the completion-persistence path."""
    return (
        not interview_active
        and not awaiting_email_confirmation
        and not completion_saved
    )
