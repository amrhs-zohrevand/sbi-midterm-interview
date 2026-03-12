from dataclasses import dataclass


INLINE_SURVEY_OPTIONS = ["Skip", "1", "2", "3", "4", "5"]


@dataclass(frozen=True)
class CompletionResponses:
    email: str
    send_email: bool
    usefulness_rating: str
    naturalness_rating: str
    feedback: str


def initialize_completion_state(session_state, recipient_email: str) -> None:
    """Populate completion-related session state with stable defaults."""
    if "completion_email" not in session_state or not str(
        session_state.completion_email
    ).strip():
        session_state.completion_email = recipient_email
    if "completion_send_email" not in session_state:
        session_state.completion_send_email = True
    if "completion_survey_usefulness" not in session_state:
        session_state.completion_survey_usefulness = "Skip"
    if "completion_survey_naturalness" not in session_state:
        session_state.completion_survey_naturalness = "Skip"
    if "completion_survey_feedback" not in session_state:
        session_state.completion_survey_feedback = ""


def normalize_survey_response(value: str) -> str:
    """Convert optional survey selections into a stored string value."""
    if not value or value == "Skip":
        return ""
    return str(value)


def build_completion_responses(session_state) -> CompletionResponses:
    """Build a normalized snapshot of the current completion-form answers."""
    return CompletionResponses(
        email=session_state.completion_email.strip(),
        send_email=bool(session_state.completion_send_email),
        usefulness_rating=normalize_survey_response(
            session_state.completion_survey_usefulness
        ),
        naturalness_rating=normalize_survey_response(
            session_state.completion_survey_naturalness
        ),
        feedback=session_state.completion_survey_feedback.strip(),
    )


def has_inline_feedback(responses: CompletionResponses) -> bool:
    """Return whether the respondent supplied any inline survey feedback."""
    return bool(
        responses.usefulness_rating
        or responses.naturalness_rating
        or responses.feedback
    )


def completion_panel_copy(interview_active: bool) -> tuple[str, str, bool]:
    """Return the title/body/can-continue text for the bottom finish panel."""
    if interview_active:
        return (
            "Finish Interview",
            "You can wrap up here, or continue the conversation if you clicked the finish button by accident.",
            True,
        )

    return (
        "Before You Go",
        "The conversation has ended. You can finish here and leave a bit of quick feedback without leaving this page.",
        False,
    )
