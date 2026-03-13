from interview_completion import CompletionResponses
from interview_persistence import (
    CompletionContext,
    CompletionResult,
    persist_completion,
    run_completion_followups,
)


def test_persist_completion_runs_foreground_pipeline_and_returns_result():
    calls = []

    def persist_local_transcript():
        calls.append(("persist_local",))
        return ("local-link", "/tmp/transcript.txt")

    def save_completion_to_sheet(*args, **kwargs):
        calls.append(("save_completion", args, kwargs))

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
        save_completion_to_sheet=save_completion_to_sheet,
        now_fn=lambda: 120.0,
        timestamp_fn=lambda: "2026-03-12 10:00:00",
    )

    assert result.transcript_link == "local-link"
    assert result.transcript_file == "/tmp/transcript.txt"
    assert result.transcript_text == "assistant: Hello\nuser: Hi\n"
    assert result.duration_minutes == "2.00"
    assert result.summary_text == ""
    assert result.email_sent is False
    assert (
        "save_completion",
        (
            "session-1",
            "s123",
            "Miros",
            "ACME",
            "midterm_interview",
            "2026-03-12 10:00:00",
            "assistant: Hello\nuser: Hi\n",
            "2.00",
        ),
        {
            "helpfulness_rating": "5",
            "connection_rating": "4",
            "understanding_rating": "6",
            "validation_rating": "7",
            "feedback": "Great ending flow.",
            "survey_timestamp": "2026-03-12 10:00:00",
        },
    ) in calls


def test_persist_completion_skips_optional_fields_on_foreground_save():
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
        save_completion_to_sheet=lambda *args, **kwargs: calls.append(
            ("save_completion", args, kwargs)
        ),
        now_fn=lambda: 120.0,
        timestamp_fn=lambda: "2026-03-12 10:00:00",
    )

    assert result.email_sent is False
    assert result.summary_text == ""
    assert calls == [
        (
            "save_completion",
            (
                "session-2",
                "",
                "Miros",
                "",
                "midterm_interview",
                "2026-03-12 10:00:00",
                "assistant: Hello\nuser: Hi\n",
                "1.00",
            ),
            {},
        )
    ]


def test_run_completion_followups_sends_email_and_updates_summary():
    calls = []

    context = CompletionContext(
        interview_id="session-1",
        student_number="s123",
        respondent_name="Miros",
        company_name="ACME",
        config_name="midterm_interview",
        recipient_email="person@example.com",
        start_time=0.0,
        messages=[],
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
    completion_result = CompletionResult(
        transcript_link="local-link",
        transcript_file="/tmp/transcript.txt",
        transcript_text="assistant: Hello\nuser: Hi\n",
        timestamp="2026-03-12 10:00:00",
        duration_minutes="2.00",
    )

    run_completion_followups(
        context,
        completion_result,
        send_transcript_email=lambda **kwargs: calls.append(("send_email", kwargs)),
        generate_summary=lambda transcript_text: calls.append(
            ("generate_summary", transcript_text)
        )
        or "summary text",
        update_interview_summary=lambda *args: calls.append(("update_summary", args)),
    )

    assert calls[0] == (
        "send_email",
        {
            "student_number": "s123",
            "recipient_email": "person@example.com",
            "transcript_link": "local-link",
            "transcript_file": "/tmp/transcript.txt",
            "name_from_form": "Miros",
        },
    )
    assert ("generate_summary", "assistant: Hello\nuser: Hi\n") in calls
    assert ("update_summary", ("session-1", "summary text")) in calls


def test_run_completion_followups_skips_optional_email_when_disabled():
    calls = []

    context = CompletionContext(
        interview_id="session-2",
        student_number="",
        respondent_name="Miros",
        company_name="",
        config_name="midterm_interview",
        recipient_email="person@example.com",
        start_time=0.0,
        messages=[],
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
    completion_result = CompletionResult(
        transcript_link="local-link",
        transcript_file="/tmp/transcript.txt",
        transcript_text="assistant: Hello\nuser: Hi\n",
        timestamp="2026-03-12 10:00:00",
        duration_minutes="2.00",
    )

    run_completion_followups(
        context,
        completion_result,
        send_transcript_email=lambda **kwargs: calls.append(("send_email", kwargs)),
        generate_summary=lambda transcript_text: "summary text",
        update_interview_summary=lambda *args: calls.append(("update_summary", args)),
    )

    assert all(call[0] != "send_email" for call in calls)
    assert calls == [("update_summary", ("session-2", "summary text"))]
