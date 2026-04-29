from remote_utils import (
    close_ssh_connection,
    ensure_remote_directory,
    get_ssh_connection,
    resolve_ssh_settings,
    run_remote_sql_batch,
    run_remote_sql,
)
from secrets_utils import get_secret


INTERVIEWS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS interviews (
    interview_id TEXT,
    student_id TEXT,
    name TEXT,
    company TEXT,
    interview_type TEXT,
    timestamp TEXT,
    transcript TEXT,
    duration_minutes TEXT,
    model TEXT,
    model_reasoning_level TEXT,
    summary TEXT,
    survey_usefulness TEXT,
    survey_naturalness TEXT,
    survey_helpfulness TEXT,
    survey_connection TEXT,
    survey_understanding TEXT,
    survey_validation TEXT,
    survey_feedback TEXT,
    survey_timestamp TEXT
)
"""

PROGRESS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS progress (
    student_id TEXT,
    name TEXT,
    interview_type TEXT,
    completion_timestamp TEXT
)
"""

CHECKPOINTS_TABLE_QUERY = """
CREATE TABLE IF NOT EXISTS interview_checkpoints (
    interview_id TEXT PRIMARY KEY,
    student_id TEXT,
    name TEXT,
    company TEXT,
    interview_type TEXT,
    last_updated TEXT,
    transcript TEXT,
    duration_minutes TEXT
)
"""

SURVEY_COLUMNS = {
    "survey_helpfulness": "TEXT",
    "survey_connection": "TEXT",
    "survey_understanding": "TEXT",
    "survey_validation": "TEXT",
    "survey_feedback": "TEXT",
    "survey_timestamp": "TEXT",
}

INTERVIEW_METADATA_COLUMNS = {
    "model": "TEXT",
    "model_reasoning_level": "TEXT",
}


def get_remote_database_location():
    """Return the remote directory and database path for interview data."""
    configured_directory = get_secret("REMOTE_DATABASE_DIRECTORY")
    if configured_directory and str(configured_directory).strip():
        remote_directory = str(configured_directory).strip().rstrip("/")
    else:
        ssh_username = resolve_ssh_settings().username
        remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"

    db_path = f"{remote_directory}/interviews.db"
    return remote_directory, db_path


def _build_interview_insert_operation(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    timestamp,
    transcript,
    duration_minutes,
    model="",
    model_reasoning_level="none",
):
    return {
        "type": "execute",
        "sql_query": """
        INSERT INTO interviews (
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            timestamp,
            transcript,
            duration_minutes,
            model,
            model_reasoning_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        "params": [
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            timestamp,
            transcript,
            duration_minutes,
            model,
            model_reasoning_level,
        ],
    }


def _build_progress_insert_operation(student_id, name, interview_type, timestamp):
    return {
        "type": "execute",
        "sql_query": """
        INSERT INTO progress (
            student_id,
            name,
            interview_type,
            completion_timestamp
        ) VALUES (?, ?, ?, ?)
        """,
        "params": [student_id, name, interview_type, timestamp],
    }


def _build_checkpoint_upsert_operation(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    last_updated,
    transcript,
    duration_minutes,
):
    return {
        "type": "execute",
        "sql_query": """
        INSERT INTO interview_checkpoints (
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            last_updated,
            transcript,
            duration_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(interview_id) DO UPDATE SET
            student_id = excluded.student_id,
            name = excluded.name,
            company = excluded.company,
            interview_type = excluded.interview_type,
            last_updated = excluded.last_updated,
            transcript = excluded.transcript,
            duration_minutes = excluded.duration_minutes
        """,
        "params": [
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            last_updated,
            transcript,
            duration_minutes,
        ],
    }


def _build_survey_update_operation(
    interview_id,
    helpfulness_rating,
    connection_rating,
    understanding_rating,
    validation_rating,
    feedback,
    survey_timestamp,
):
    return {
        "type": "execute",
        "sql_query": """
        UPDATE interviews
        SET survey_helpfulness = ?,
            survey_connection = ?,
            survey_understanding = ?,
            survey_validation = ?,
            survey_feedback = ?,
            survey_timestamp = ?
        WHERE interview_id = ?
        """,
        "params": [
            helpfulness_rating,
            connection_rating,
            understanding_rating,
            validation_rating,
            feedback,
            survey_timestamp,
            interview_id,
        ],
    }


def _run_batch_operations(*, operations, ensure_remote_dir=False):
    remote_directory, db_path = get_remote_database_location()

    ssh, tmp_key_path = get_ssh_connection()
    try:
        if ensure_remote_dir:
            ensure_remote_directory(ssh, remote_directory)
        return run_remote_sql_batch(ssh, db_path, operations)
    finally:
        close_ssh_connection(ssh, tmp_key_path)


def persist_completion_remote(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    timestamp,
    transcript,
    duration_minutes,
    *,
    model="",
    model_reasoning_level="none",
    helpfulness_rating="",
    connection_rating="",
    understanding_rating="",
    validation_rating="",
    feedback="",
    survey_timestamp="",
):
    """Persist completion-time interview data in one remote save operation."""
    operations = [
        {"type": "execute", "sql_query": INTERVIEWS_TABLE_QUERY},
        {
            "type": "ensure_columns",
            "table": "interviews",
            "columns": INTERVIEW_METADATA_COLUMNS,
        },
        _build_interview_insert_operation(
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            timestamp,
            transcript,
            duration_minutes,
            model,
            model_reasoning_level,
        ),
    ]

    if student_id:
        operations.extend(
            [
                {"type": "execute", "sql_query": PROGRESS_TABLE_QUERY},
                _build_progress_insert_operation(
                    student_id, name, interview_type, timestamp
                ),
            ]
        )

    if survey_timestamp:
        operations.extend(
            [
                {
                    "type": "ensure_columns",
                    "table": "interviews",
                    "columns": SURVEY_COLUMNS,
                },
                _build_survey_update_operation(
                    interview_id,
                    helpfulness_rating,
                    connection_rating,
                    understanding_rating,
                    validation_rating,
                    feedback,
                    survey_timestamp,
                ),
            ]
        )

    _run_batch_operations(operations=operations, ensure_remote_dir=True)


def persist_checkpoint_remote(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    last_updated,
    transcript,
    duration_minutes,
):
    """Upsert an in-progress transcript checkpoint in the remote SQLite database."""
    _run_batch_operations(
        operations=[
            {"type": "execute", "sql_query": CHECKPOINTS_TABLE_QUERY},
            _build_checkpoint_upsert_operation(
                interview_id,
                student_id,
                name,
                company,
                interview_type,
                last_updated,
                transcript,
                duration_minutes,
            ),
        ],
        ensure_remote_dir=True,
    )


def save_interview_to_sheet(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    timestamp,
    transcript,
    duration_minutes,
    model="",
    model_reasoning_level="none",
):
    """
    Insert the interview data into the remote SQLite database.

    The database file (interviews.db) is located in the SSH directory.
    """
    _run_batch_operations(
        operations=[
            {"type": "execute", "sql_query": INTERVIEWS_TABLE_QUERY},
            {
                "type": "ensure_columns",
                "table": "interviews",
                "columns": INTERVIEW_METADATA_COLUMNS,
            },
            _build_interview_insert_operation(
                interview_id,
                student_id,
                name,
                company,
                interview_type,
                timestamp,
                transcript,
                duration_minutes,
                model,
                model_reasoning_level,
            ),
        ],
        ensure_remote_dir=True,
    )


def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Insert a progress update into the remote SQLite database.

    The database file (interviews.db) is located in the SSH directory.
    """
    _run_batch_operations(
        operations=[
            {"type": "execute", "sql_query": PROGRESS_TABLE_QUERY},
            _build_progress_insert_operation(
                student_id, name, interview_type, timestamp
            ),
        ],
        ensure_remote_dir=True,
    )


def get_transcript_by_student_and_type(student_id, interview_type, ssh_conn=None):
    """
    Retrieve the most recent summary for a student and interview type.

    Accepts an optional SSH connection. Returns an empty string if not found.
    """
    _, db_path = get_remote_database_location()

    remove_after = False
    if ssh_conn is None:
        ssh, tmp_key_path = get_ssh_connection()
        remove_after = True
    else:
        ssh = ssh_conn
        tmp_key_path = None

    try:
        query = """
        SELECT summary
        FROM interviews
        WHERE student_id = ? AND interview_type = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """
        row = run_remote_sql(
            ssh,
            db_path,
            query,
            [student_id, interview_type],
            fetch="one",
        )
        return row[0] if row and row[0] else ""
    finally:
        if remove_after:
            close_ssh_connection(ssh, tmp_key_path)


def update_interview_summary(interview_id, summary):
    """Update the stored summary for a completed interview."""
    _, db_path = get_remote_database_location()

    ssh, tmp_key_path = get_ssh_connection()
    try:
        update_query = """
        UPDATE interviews
        SET summary = ?
        WHERE interview_id = ?
        """
        run_remote_sql(ssh, db_path, update_query, [summary, interview_id])
    finally:
        close_ssh_connection(ssh, tmp_key_path)


def update_interview_survey(
    interview_id,
    helpfulness_rating,
    connection_rating,
    understanding_rating,
    validation_rating,
    feedback,
    survey_timestamp,
):
    """Update the stored inline survey responses for a completed interview."""
    _run_batch_operations(
        operations=[
            {
                "type": "ensure_columns",
                "table": "interviews",
                "columns": SURVEY_COLUMNS,
            },
            _build_survey_update_operation(
                interview_id,
                helpfulness_rating,
                connection_rating,
                understanding_rating,
                validation_rating,
                feedback,
                survey_timestamp,
            ),
        ]
    )
