from interview_configs import (
    end_reflection_interview,
    industry_org_survey,
    midterm_interview,
)


def test_interview_configs_disable_random_reasoning_by_default():
    assert industry_org_survey.RANDOM_REASONING_EXPERIMENT is False
    assert midterm_interview.RANDOM_REASONING_EXPERIMENT is False
    assert end_reflection_interview.RANDOM_REASONING_EXPERIMENT is False
