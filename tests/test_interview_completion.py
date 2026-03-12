from interview_completion import (
    CompletionResponses,
    build_completion_responses,
    completion_panel_copy,
    has_inline_feedback,
    initialize_completion_state,
    normalize_survey_response,
)


class FakeSessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_initialize_completion_state_sets_defaults_once():
    session_state = FakeSessionState()
    initialize_completion_state(session_state, "person@example.com")

    assert session_state.completion_email == "person@example.com"
    assert session_state.completion_send_email is False
    assert session_state.completion_survey_usefulness == "Skip"
    assert session_state.completion_survey_naturalness == "Skip"
    assert session_state.completion_survey_feedback == ""

    session_state.completion_email = "updated@example.com"
    initialize_completion_state(session_state, "new@example.com")
    assert session_state.completion_email == "updated@example.com"


def test_normalize_survey_response_treats_skip_as_empty():
    assert normalize_survey_response("Skip") == ""
    assert normalize_survey_response("") == ""
    assert normalize_survey_response("4") == "4"


def test_build_completion_responses_normalizes_state_values():
    session_state = FakeSessionState(
        completion_email="person@example.com",
        completion_send_email=True,
        completion_survey_usefulness="5",
        completion_survey_naturalness="Skip",
        completion_survey_feedback="  Nice flow.  ",
    )

    responses = build_completion_responses(session_state)

    assert responses == CompletionResponses(
        email="person@example.com",
        send_email=True,
        usefulness_rating="5",
        naturalness_rating="",
        feedback="Nice flow.",
    )


def test_has_inline_feedback_detects_any_answer():
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "", "", "")
    ) is False
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "4", "", "")
    ) is True
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "", "", "Needs polish")
    ) is True


def test_completion_panel_copy_reflects_manual_vs_natural_end():
    assert completion_panel_copy(True)[0] == "Finish Interview"
    assert completion_panel_copy(True)[2] is True
    assert completion_panel_copy(False)[0] == "Before You Go"
    assert completion_panel_copy(False)[2] is False
