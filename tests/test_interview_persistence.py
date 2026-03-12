from interview_completion import CompletionResponses
from interview_persistence import CompletionContext, persist_completion


def test_persist_completion_runs_full_pipeline_and_returns_result():
    calls = []

    def persist_local_transcript():
        calls.append(("persist_local",))
        return ("local-link", "/tmp/transcript.txt")

    def send_transcript_email(**kwargs):
        calls.append(("send_email", kwargs))

    def save_interview_to_sheet(*args):
        calls.append(("save_interview", args))

    def update_progress_sheet(*args):
        calls.append(("update_progress", args))

    def generate_summary(transcript_text):
        calls.append(("generate_summary", transcript_text))
        return "summary text"

    def update_interview_summary(*args):
        calls.append(("update_summary", args))

    def update_interview_survey(*args):
        calls.append(("update_survey", args))

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
        send_transcript_email=send_transcript_email,
        save_interview_to_sheet=save_interview_to_sheet,
        update_progress_sheet=update_progress_sheet,
        generate_summary=generate_summary,
        update_interview_summary=update_interview_summary,
        update_interview_survey=update_interview_survey,
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
    assert any(call[0] == "update_progress" for call in calls)
    assert (
        "update_survey",
        (
            "session-1",
            "5",
            "4",
            "6",
            "7",
            "Great ending flow.",
            "2026-03-12 10:00:00",
        ),
    ) in calls


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
        save_interview_to_sheet=lambda *args: calls.append(("save_interview", args)),
        update_progress_sheet=lambda *args: calls.append(("update_progress", args)),
        generate_summary=lambda transcript_text: "summary text",
        update_interview_summary=lambda *args: calls.append(("update_summary", args)),
        update_interview_survey=lambda *args: calls.append(("update_survey", args)),
        now_fn=lambda: 120.0,
        timestamp_fn=lambda: "2026-03-12 10:00:00",
    )

    assert result.email_sent is False
    assert all(call[0] != "send_email" for call in calls)
    assert all(call[0] != "update_progress" for call in calls)
    assert all(call[0] != "update_survey" for call in calls)
