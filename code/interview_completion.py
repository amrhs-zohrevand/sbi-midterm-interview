from dataclasses import dataclass


INLINE_SURVEY_OPTIONS = ["1", "2", "3", "4", "5", "6", "7"]
INLINE_SURVEY_LEGEND = (
    "Rate each statement from 1 to 7 (1 = not at all, 7 = extremely)."
)


@dataclass(frozen=True)
class CompletionResponses:
    email: str
    send_email: bool
    helpfulness_rating: str
    connection_rating: str
    understanding_rating: str
    validation_rating: str
    feedback: str


def initialize_completion_state(session_state, recipient_email: str) -> None:
    """Populate completion-related session state with stable defaults."""
    if "completion_email" not in session_state or not str(
        session_state.completion_email
    ).strip():
        session_state.completion_email = recipient_email
    if "completion_send_email" not in session_state:
        session_state.completion_send_email = True
    if "completion_survey_helpfulness" not in session_state:
        session_state.completion_survey_helpfulness = ""
    if "completion_survey_connection" not in session_state:
        session_state.completion_survey_connection = ""
    if "completion_survey_understanding" not in session_state:
        session_state.completion_survey_understanding = ""
    if "completion_survey_validation" not in session_state:
        session_state.completion_survey_validation = ""
    if "completion_survey_feedback" not in session_state:
        session_state.completion_survey_feedback = ""


def normalize_survey_response(value) -> str:
    """Convert optional survey selections into a stored string value."""
    if not value or value == "Skip":
        return ""
    return str(value)


def survey_option_index(value) -> int | None:
    """Return a safe radio index for the inline survey options."""
    try:
        return INLINE_SURVEY_OPTIONS.index(value)
    except ValueError:
        return None


def build_completion_responses(session_state) -> CompletionResponses:
    """Build a normalized snapshot of the current completion-form answers."""
    return CompletionResponses(
        email=session_state.completion_email.strip(),
        send_email=bool(session_state.completion_send_email),
        helpfulness_rating=normalize_survey_response(
            session_state.completion_survey_helpfulness
        ),
        connection_rating=normalize_survey_response(
            session_state.completion_survey_connection
        ),
        understanding_rating=normalize_survey_response(
            session_state.completion_survey_understanding
        ),
        validation_rating=normalize_survey_response(
            session_state.completion_survey_validation
        ),
        feedback=session_state.completion_survey_feedback.strip(),
    )


def has_inline_feedback(responses: CompletionResponses) -> bool:
    """Return whether the respondent supplied any inline survey feedback."""
    return bool(
        responses.helpfulness_rating
        or responses.connection_rating
        or responses.understanding_rating
        or responses.validation_rating
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
