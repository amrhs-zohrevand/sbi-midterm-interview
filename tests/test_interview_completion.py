from interview_completion import (
    CompletionResponses,
    INLINE_SURVEY_LEGEND,
    build_completion_responses,
    completion_panel_copy,
    has_inline_feedback,
    initialize_completion_state,
    normalize_survey_response,
    survey_option_index,
)


class FakeSessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_initialize_completion_state_sets_defaults_once():
    session_state = FakeSessionState()
    initialize_completion_state(session_state, "person@example.com")

    assert session_state.completion_email == "person@example.com"
    assert session_state.completion_send_email is True
    assert session_state.completion_survey_helpfulness == ""
    assert session_state.completion_survey_connection == ""
    assert session_state.completion_survey_understanding == ""
    assert session_state.completion_survey_validation == ""
    assert session_state.completion_survey_feedback == ""

    session_state.completion_email = "updated@example.com"
    initialize_completion_state(session_state, "new@example.com")
    assert session_state.completion_email == "updated@example.com"


def test_initialize_completion_state_restores_blank_email_from_recipient():
    session_state = FakeSessionState(completion_email="   ")

    initialize_completion_state(session_state, "person@example.com")

    assert session_state.completion_email == "person@example.com"


def test_normalize_survey_response_treats_skip_as_empty():
    assert normalize_survey_response("Skip") == ""
    assert normalize_survey_response("") == ""
    assert normalize_survey_response(None) == ""
    assert normalize_survey_response("4") == "4"


def test_build_completion_responses_normalizes_state_values():
    session_state = FakeSessionState(
        completion_email="person@example.com",
        completion_send_email=True,
        completion_survey_helpfulness="5",
        completion_survey_connection="6",
        completion_survey_understanding="7",
        completion_survey_validation="",
        completion_survey_feedback="  Nice flow.  ",
    )

    responses = build_completion_responses(session_state)

    assert responses == CompletionResponses(
        email="person@example.com",
        send_email=True,
        helpfulness_rating="5",
        connection_rating="6",
        understanding_rating="7",
        validation_rating="",
        feedback="Nice flow.",
    )


def test_build_completion_responses_trims_email():
    session_state = FakeSessionState(
        completion_email="  person@example.com  ",
        completion_send_email=True,
        completion_survey_helpfulness=None,
        completion_survey_connection="",
        completion_survey_understanding="",
        completion_survey_validation="",
        completion_survey_feedback="",
    )

    responses = build_completion_responses(session_state)

    assert responses.email == "person@example.com"
    assert responses.helpfulness_rating == ""
    assert responses.connection_rating == ""
    assert responses.understanding_rating == ""
    assert responses.validation_rating == ""


def test_survey_option_index_returns_none_for_blank_or_unknown_values():
    assert survey_option_index("1") == 0
    assert survey_option_index("7") == 6
    assert survey_option_index("Skip") is None
    assert survey_option_index("unexpected") is None


def test_has_inline_feedback_detects_any_answer():
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "", "", "", "", "")
    ) is False
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "4", "", "", "", "")
    ) is True
    assert has_inline_feedback(
        CompletionResponses("a@example.com", False, "", "", "", "", "Needs polish")
    ) is True


def test_completion_panel_copy_reflects_manual_vs_natural_end():
    assert completion_panel_copy(True)[0] == "Finish Interview"
    assert completion_panel_copy(True)[2] is True
    assert completion_panel_copy(False)[0] == "Before You Go"
    assert completion_panel_copy(False)[2] is False


def test_inline_survey_legend_matches_condensed_scale_copy():
    assert INLINE_SURVEY_LEGEND == (
        "Rate each statement from 1 to 7 (1 = not at all, 7 = extremely)."
    )
