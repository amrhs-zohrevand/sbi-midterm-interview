def normalize_query_value(value, default="") -> str:
    """Normalize a Streamlit query-param value to a plain string."""
    if isinstance(value, list):
        value = value[0] if value else default
    if value is None:
        value = default
    return str(value)


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


def filter_display_messages(messages, closing_messages):
    """Return the subset of messages that should appear in the chat UI."""
    visible_messages = []
    for message in messages:
        if message["role"] == "system":
            continue
        if find_closing_code(message["content"], closing_messages):
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
