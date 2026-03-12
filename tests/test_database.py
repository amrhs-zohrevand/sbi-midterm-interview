import database


def test_save_interview_to_sheet_uses_parameterized_insert(monkeypatch):
    calls = []
    fake_ssh = object()

    monkeypatch.setattr(
        database,
        "get_remote_database_location",
        lambda: ("/remote/data", "/remote/data/interviews.db"),
    )
    monkeypatch.setattr(database, "get_ssh_connection", lambda: (fake_ssh, "/tmp/key"))
    monkeypatch.setattr(
        database,
        "ensure_remote_directory",
        lambda ssh, path: calls.append(("mkdir", path)),
    )
    monkeypatch.setattr(
        database,
        "run_remote_sql",
        lambda ssh, db_path, sql, params=None, fetch=None: calls.append(
            ("sql", db_path, " ".join(sql.split()), params, fetch)
        ),
    )
    cleanup = []
    monkeypatch.setattr(
        database,
        "close_ssh_connection",
        lambda ssh, key_path: cleanup.append((ssh, key_path)),
    )

    database.save_interview_to_sheet(
        "interview-1",
        "student-1",
        "Miros O'Connor",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello",
        "12.50",
    )

    assert calls[0] == ("mkdir", "/remote/data")
    assert "CREATE TABLE IF NOT EXISTS interviews" in calls[1][2]
    assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?)" in calls[2][2]
    assert calls[2][3] == [
        "interview-1",
        "student-1",
        "Miros O'Connor",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello",
        "12.50",
    ]
    assert cleanup == [(fake_ssh, "/tmp/key")]


def test_get_transcript_by_student_and_type_returns_summary_text(monkeypatch):
    fake_ssh = object()
    monkeypatch.setattr(
        database,
        "get_remote_database_location",
        lambda: ("/remote/data", "/remote/data/interviews.db"),
    )
    monkeypatch.setattr(database, "get_ssh_connection", lambda: (fake_ssh, "/tmp/key"))
    monkeypatch.setattr(
        database,
        "run_remote_sql",
        lambda ssh, db_path, sql, params=None, fetch=None: ["summary text"],
    )
    cleanup = []
    monkeypatch.setattr(
        database,
        "close_ssh_connection",
        lambda ssh, key_path: cleanup.append((ssh, key_path)),
    )

    result = database.get_transcript_by_student_and_type(
        "student-1", "midterm_interview"
    )

    assert result == "summary text"
    assert cleanup == [(fake_ssh, "/tmp/key")]


def test_update_progress_and_summary_use_parameterized_queries(monkeypatch):
    calls = []
    fake_ssh = object()

    monkeypatch.setattr(
        database,
        "get_remote_database_location",
        lambda: ("/remote/data", "/remote/data/interviews.db"),
    )
    monkeypatch.setattr(database, "get_ssh_connection", lambda: (fake_ssh, "/tmp/key"))
    monkeypatch.setattr(database, "ensure_remote_directory", lambda *args: None)
    monkeypatch.setattr(
        database,
        "run_remote_sql",
        lambda ssh, db_path, sql, params=None, fetch=None: calls.append(
            (" ".join(sql.split()), params)
        ),
    )
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.update_progress_sheet(
        "student-1", "Miros", "midterm_interview", "2026-03-12 10:00:00"
    )
    database.update_interview_summary("interview-1", "summary text")

    assert any("VALUES (?, ?, ?, ?)" in sql for sql, _ in calls)
    assert any(params == ["summary text", "interview-1"] for _, params in calls)


def test_update_interview_survey_adds_missing_columns_and_saves_answers(monkeypatch):
    calls = []
    fake_ssh = object()

    monkeypatch.setattr(
        database,
        "get_remote_database_location",
        lambda: ("/remote/data", "/remote/data/interviews.db"),
    )
    monkeypatch.setattr(database, "get_ssh_connection", lambda: (fake_ssh, "/tmp/key"))

    def fake_run_remote_sql(ssh, db_path, sql, params=None, fetch=None):
        normalized_sql = " ".join(sql.split())
        calls.append((normalized_sql, params, fetch))
        if "PRAGMA table_info(interviews)" in normalized_sql:
            return [
                [0, "interview_id", "TEXT", 0, None, 0],
                [1, "summary", "TEXT", 0, None, 0],
            ]
        return None

    monkeypatch.setattr(database, "run_remote_sql", fake_run_remote_sql)
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.update_interview_survey(
        "interview-1",
        "5",
        "4",
        "Much smoother at the end now.",
        "2026-03-12 10:00:00",
    )

    assert any(
        "ALTER TABLE interviews ADD COLUMN survey_usefulness TEXT" in sql
        for sql, _, _ in calls
    )
    assert any(
        "ALTER TABLE interviews ADD COLUMN survey_naturalness TEXT" in sql
        for sql, _, _ in calls
    )
    assert any(
        "ALTER TABLE interviews ADD COLUMN survey_feedback TEXT" in sql
        for sql, _, _ in calls
    )
    assert any(
        params
        == [
            "5",
            "4",
            "Much smoother at the end now.",
            "2026-03-12 10:00:00",
            "interview-1",
        ]
        for _, params, _ in calls
    )
