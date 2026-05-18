from interview_completion import CompletionResponses
from interview_persistence import CompletionContext, persist_completion


def test_persist_completion_runs_full_pipeline_and_returns_result():
    calls = []

    def persist_local_transcript():
        calls.append(("persist_local",))
        return ("local-link", "/tmp/transcript.txt")

    def send_transcript_email(**kwargs):
        calls.append(("send_email", kwargs))

    def persist_remote_completion(*args, **kwargs):
        calls.append(("persist_remote", args, kwargs))

    def generate_summary(transcript_text):
        calls.append(("generate_summary", transcript_text))
        return "summary text"

    def update_interview_summary(*args):
        calls.append(("update_summary", args))

    context = CompletionContext(
        interview_id="session-1",
        student_number="s123",
        respondent_name="Miros",
        company_name="ACME",
        config_name="midterm_interview",
        recipient_email="person@example.com",
        start_time=0.0,
        messages=[
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Hi"},
        ],
        model="openai/gpt-5.4",
        model_reasoning_level="medium",
        completion_responses=CompletionResponses(
            email="person@example.com",
            send_email=True,
            helpfulness_rating="5",
            connection_rating="4",
            understanding_rating="6",
            validation_rating="7",
            feedback="Great ending flow.",
        ),
    )

    result = persist_completion(
        context,
        persist_local_transcript=persist_local_transcript,
        send_transcript_email=send_transcript_email,
        persist_remote_completion=persist_remote_completion,
        generate_summary=generate_summary,
        update_interview_summary=update_interview_summary,
        now_fn=lambda: 120.0,
        timestamp_fn=lambda: "2026-03-12 10:00:00",
    )

    assert result.transcript_link == "local-link"
    assert result.transcript_file == "/tmp/transcript.txt"
    assert result.transcript_text == "assistant: Hello\nuser: Hi\n"
    assert result.duration_minutes == "2.00"
    assert result.summary_text == "summary text"
    assert result.email_sent is True
    assert any(call[0] == "send_email" for call in calls)
    persist_remote_call = next(call for call in calls if call[0] == "persist_remote")
    assert persist_remote_call[1] == (
        "session-1",
        "s123",
        "Miros",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello\nuser: Hi\n",
        "2.00",
    )
    assert persist_remote_call[2] == {
        "helpfulness_rating": "5",
        "connection_rating": "4",
        "understanding_rating": "6",
        "validation_rating": "7",
        "feedback": "Great ending flow.",
        "survey_timestamp": "2026-03-12 10:00:00",
        "model": "openai/gpt-5.4",
        "model_reasoning_level": "medium",
    }


def test_persist_completion_skips_optional_steps_when_not_needed():
    calls = []

    context = CompletionContext(
        interview_id="session-2",
        student_number="",
        respondent_name="Miros",
        company_name="",
        config_name="midterm_interview",
        recipient_email="person@example.com",
        start_time=60.0,
        messages=[
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Hi"},
        ],
        completion_responses=CompletionResponses(
            email="person@example.com",
            send_email=False,
            helpfulness_rating="",
            connection_rating="",
            understanding_rating="",
            validation_rating="",
            feedback="",
        ),
    )

    result = persist_completion(
        context,
        persist_local_transcript=lambda: ("", "/tmp/transcript.txt"),
        send_transcript_email=lambda **kwargs: calls.append(("send_email", kwargs)),
        persist_remote_completion=lambda *args, **kwargs: calls.append(
            ("persist_remote", args, kwargs)
        ),
        generate_summary=lambda transcript_text: "summary text",
        update_interview_summary=lambda *args: calls.append(("update_summary", args)),
        now_fn=lambda: 120.0,
        timestamp_fn=lambda: "2026-03-12 10:00:00",
    )

    assert result.email_sent is False
    assert all(call[0] != "send_email" for call in calls)
    persist_remote_call = next(call for call in calls if call[0] == "persist_remote")
    assert persist_remote_call[1] == (
        "session-2",
        "",
        "Miros",
        "",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello\nuser: Hi\n",
        "1.00",
    )
    assert persist_remote_call[2]["survey_timestamp"] == ""
    assert persist_remote_call[2]["model"] == ""
    assert persist_remote_call[2]["model_reasoning_level"] == "none"
