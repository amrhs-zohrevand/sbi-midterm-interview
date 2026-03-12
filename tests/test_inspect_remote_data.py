from types import SimpleNamespace

import pytest

from inspect_remote_data import build_query


def test_build_query_filters_by_session_id():
    args = SimpleNamespace(
        table="interviews",
        limit=5,
        student_id="",
        interview_type="industry_org_survey",
        interview_id="session-123",
        count_only=False,
        show_summary=False,
        show_transcript=False,
    )

    query, params, columns = build_query(args)

    assert "interview_id = ?" in query
    assert "interview_type = ?" in query
    assert params == ["session-123", "industry_org_survey", 5]
    assert columns[0] == "interview_id"


def test_build_query_rejects_session_id_for_progress_table():
    args = SimpleNamespace(
        table="progress",
        limit=5,
        student_id="",
        interview_type="",
        interview_id="session-123",
        count_only=False,
        show_summary=False,
        show_transcript=False,
    )

    with pytest.raises(ValueError, match="--session-id"):
        build_query(args)
