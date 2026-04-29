import database
from remote_utils import SshSettings


def test_get_remote_database_location_uses_resolved_username(monkeypatch):
    monkeypatch.setattr(database, "get_secret", lambda key, default=None: default)
    monkeypatch.setattr(
        database,
        "resolve_ssh_settings",
        lambda: SshSettings(
            host="510530198.ssh.w1.strato.hosting",
            username="stu61498987",
            key="test-key",
        ),
    )

    remote_directory, db_path = database.get_remote_database_location()

    assert remote_directory == "/home/stu61498987/BS-Interviews/Database"
    assert db_path == "/home/stu61498987/BS-Interviews/Database/interviews.db"


def test_get_remote_database_location_allows_directory_override(monkeypatch):
    monkeypatch.setattr(
        database,
        "get_secret",
        lambda key, default=None: "/home/stu61498987/custom-db/"
        if key == "REMOTE_DATABASE_DIRECTORY"
        else default,
    )

    remote_directory, db_path = database.get_remote_database_location()

    assert remote_directory == "/home/stu61498987/custom-db"
    assert db_path == "/home/stu61498987/custom-db/interviews.db"


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
        "run_remote_sql_batch",
        lambda ssh, db_path, operations: calls.append(
            (
                "batch",
                db_path,
                [
                    (
                        operation["type"],
                        " ".join(operation.get("sql_query", "").split()),
                        operation.get("params"),
                        operation.get("columns"),
                    )
                    for operation in operations
                ],
            )
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
    assert calls[1][0] == "batch"
    assert "CREATE TABLE IF NOT EXISTS interviews" in calls[1][2][0][1]
    assert calls[1][2][1] == (
        "ensure_columns",
        "",
        None,
        database.INTERVIEW_METADATA_COLUMNS,
    )
    assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)" in calls[1][2][2][1]
    assert calls[1][2][2][2] == [
        "interview-1",
        "student-1",
        "Miros O'Connor",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello",
        "12.50",
        "",
        "none",
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
    batch_calls = []
    summary_calls = []
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
        "run_remote_sql_batch",
        lambda ssh, db_path, operations: batch_calls.append(
            [
                (" ".join(operation.get("sql_query", "").split()), operation.get("params"))
                for operation in operations
            ]
        ),
    )
    monkeypatch.setattr(
        database,
        "run_remote_sql",
        lambda ssh, db_path, sql, params=None, fetch=None: summary_calls.append(
            (" ".join(sql.split()), params)
        ),
    )
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.update_progress_sheet(
        "student-1", "Miros", "midterm_interview", "2026-03-12 10:00:00"
    )
    database.update_interview_summary("interview-1", "summary text")

    assert any(
        "VALUES (?, ?, ?, ?)" in sql for sql, _ in batch_calls[0]
    )
    assert any(
        params == ["summary text", "interview-1"] for _, params in summary_calls
    )


def test_update_interview_survey_adds_missing_columns_and_saves_answers(monkeypatch):
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
        "run_remote_sql_batch",
        lambda ssh, db_path, operations: calls.extend(operations),
    )
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.update_interview_survey(
        "interview-1",
        "5",
        "4",
        "6",
        "7",
        "Much smoother at the end now.",
        "2026-03-12 10:00:00",
    )

    assert calls[0] == {
        "type": "ensure_columns",
        "table": "interviews",
        "columns": database.SURVEY_COLUMNS,
    }
    assert calls[1]["params"] == [
        "5",
        "4",
        "6",
        "7",
        "Much smoother at the end now.",
        "2026-03-12 10:00:00",
        "interview-1",
    ]


def test_persist_completion_remote_batches_interview_progress_and_survey(monkeypatch):
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
        "run_remote_sql_batch",
        lambda ssh, db_path, operations: calls.append(("batch", db_path, operations)),
    )
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.persist_completion_remote(
        "interview-1",
        "student-1",
        "Miros",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:00:00",
        "assistant: Hello",
        "12.50",
        model="openai/gpt-5.4",
        model_reasoning_level="medium",
        helpfulness_rating="5",
        connection_rating="4",
        understanding_rating="6",
        validation_rating="7",
        feedback="Great ending flow.",
        survey_timestamp="2026-03-12 10:00:00",
    )

    assert calls[0] == ("mkdir", "/remote/data")
    operations = calls[1][2]
    assert len(operations) == 7
    assert "CREATE TABLE IF NOT EXISTS interviews" in operations[0]["sql_query"]
    assert operations[1] == {
        "type": "ensure_columns",
        "table": "interviews",
        "columns": database.INTERVIEW_METADATA_COLUMNS,
    }
    assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)" in operations[2]["sql_query"]
    assert operations[2]["params"][-2:] == ["openai/gpt-5.4", "medium"]
    assert "CREATE TABLE IF NOT EXISTS progress" in operations[3]["sql_query"]
    assert operations[4]["params"] == [
        "student-1",
        "Miros",
        "midterm_interview",
        "2026-03-12 10:00:00",
    ]
    assert operations[5] == {
        "type": "ensure_columns",
        "table": "interviews",
        "columns": database.SURVEY_COLUMNS,
    }
    assert operations[6]["params"] == [
        "5",
        "4",
        "6",
        "7",
        "Great ending flow.",
        "2026-03-12 10:00:00",
        "interview-1",
    ]


def test_persist_checkpoint_remote_upserts_in_progress_transcript(monkeypatch):
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
        "run_remote_sql_batch",
        lambda ssh, db_path, operations: calls.append(("batch", db_path, operations)),
    )
    monkeypatch.setattr(database, "close_ssh_connection", lambda *args: None)

    database.persist_checkpoint_remote(
        "interview-1",
        "student-1",
        "Miros",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:01:00",
        "assistant: Hello\nuser: Hi\n",
        "1.00",
    )

    assert calls[0] == ("mkdir", "/remote/data")
    operations = calls[1][2]
    assert len(operations) == 2
    assert (
        "CREATE TABLE IF NOT EXISTS interview_checkpoints"
        in operations[0]["sql_query"]
    )
    assert "ON CONFLICT(interview_id) DO UPDATE SET" in operations[1]["sql_query"]
    assert operations[1]["params"] == [
        "interview-1",
        "student-1",
        "Miros",
        "ACME",
        "midterm_interview",
        "2026-03-12 10:01:00",
        "assistant: Hello\nuser: Hi\n",
        "1.00",
    ]
