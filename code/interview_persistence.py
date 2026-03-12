from dataclasses import dataclass
from time import localtime, strftime, time as current_time

from interview_completion import CompletionResponses, has_inline_feedback
from interview_logic import serialize_transcript


@dataclass(frozen=True)
class CompletionContext:
    interview_id: str
    student_number: str
    respondent_name: str
    company_name: str
    config_name: str
    recipient_email: str
    start_time: float
    messages: list[dict]
    completion_responses: CompletionResponses


@dataclass(frozen=True)
class CompletionResult:
    transcript_link: str
    transcript_file: str
    transcript_text: str
    timestamp: str
    duration_minutes: str
    summary_text: str
    email_sent: bool


def persist_completion(
    context: CompletionContext,
    *,
    persist_local_transcript,
    send_transcript_email,
    save_interview_to_sheet,
    update_progress_sheet,
    generate_summary,
    update_interview_summary,
    update_interview_survey,
    now_fn=current_time,
    timestamp_fn=None,
):
    """Persist the completed interview using the provided side-effect callbacks."""
    timestamp_fn = timestamp_fn or (
        lambda: strftime("%Y-%m-%d %H:%M:%S", localtime(now_fn()))
    )

    transcript_link, transcript_file = persist_local_transcript()
    email_sent = False
    if context.completion_responses.send_email:
        send_transcript_email(
            student_number=context.student_number,
            recipient_email=context.completion_responses.email or context.recipient_email,
            transcript_link=transcript_link,
            transcript_file=transcript_file,
            name_from_form=context.respondent_name,
        )
        email_sent = True

    duration_minutes_value = (now_fn() - context.start_time) / 60
    duration_minutes = f"{duration_minutes_value:.2f}"
    timestamp = timestamp_fn()
    transcript_text = serialize_transcript(context.messages)

    save_interview_to_sheet(
        context.interview_id,
        context.student_number,
        context.respondent_name,
        context.company_name,
        context.config_name,
        timestamp,
        transcript_text,
        duration_minutes,
    )
    if context.student_number:
        update_progress_sheet(
            context.student_number,
            context.respondent_name,
            context.config_name,
            timestamp,
        )

    summary_text = generate_summary(transcript_text)
    update_interview_summary(context.interview_id, summary_text)

    if has_inline_feedback(context.completion_responses):
        update_interview_survey(
            context.interview_id,
            context.completion_responses.usefulness_rating,
            context.completion_responses.naturalness_rating,
            context.completion_responses.feedback,
            timestamp,
        )

    return CompletionResult(
        transcript_link=transcript_link,
        transcript_file=transcript_file,
        transcript_text=transcript_text,
        timestamp=timestamp,
        duration_minutes=duration_minutes,
        summary_text=summary_text,
        email_sent=email_sent,
    )
