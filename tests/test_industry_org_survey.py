from interview_configs import industry_org_survey


def test_industry_org_survey_retains_scenarios_and_closing_question():
    outline = industry_org_survey.INTERVIEW_OUTLINE
    assert "Scenario 1:" in outline
    assert "Scenario 2:" in outline
    assert (
        'Is there anything else about AI in your work that we haven\'t discussed and you\'d like to mention?'
        in outline
    )


def test_industry_org_survey_locks_in_follow_up_guardrails():
    outline = industry_org_survey.INTERVIEW_OUTLINE
    assert "During these scenario discussions, ask only one question at a time." in outline
    assert "After Scenario 1, ask at most one follow-up before moving to Scenario 2." in outline
    assert "After Scenario 2, ask at most one follow-up before moving toward closing." in outline
    assert (
        "If the respondent introduces a criterion such as confidentiality, copyright, company policy, personal effort, or ownership, probe that criterion once before concluding."
        in outline
    )
    assert (
        "Do not end the interview in the same turn in which the respondent introduces a new substantive distinction."
        in outline
    )
