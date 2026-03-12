from remote_utils import (
    close_ssh_connection,
    ensure_remote_directory,
    get_ssh_connection,
    run_remote_sql,
)
from secrets_utils import get_secret


def get_remote_database_location():
    """Return the remote directory and database path for interview data."""
    ssh_username = get_secret("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")

    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"
    return remote_directory, db_path


def save_interview_to_sheet(
    interview_id,
    student_id,
    name,
    company,
    interview_type,
    timestamp,
    transcript,
    duration_minutes,
):
    """
    Insert the interview data into the remote SQLite database.

    The database file (interviews.db) is located in the SSH directory.
    """
    remote_directory, db_path = get_remote_database_location()

    ssh, tmp_key_path = get_ssh_connection()
    try:
        ensure_remote_directory(ssh, remote_directory)
        create_table_query = """
        CREATE TABLE IF NOT EXISTS interviews (
            interview_id TEXT,
            student_id TEXT,
            name TEXT,
            company TEXT,
            interview_type TEXT,
            timestamp TEXT,
            transcript TEXT,
            duration_minutes TEXT,
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
        run_remote_sql(ssh, db_path, create_table_query)

        insert_query = """
        INSERT INTO interviews (
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            timestamp,
            transcript,
            duration_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        run_remote_sql(
            ssh,
            db_path,
            insert_query,
            [
                interview_id,
                student_id,
                name,
                company,
                interview_type,
                timestamp,
                transcript,
                duration_minutes,
            ],
        )
    finally:
        close_ssh_connection(ssh, tmp_key_path)


def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Insert a progress update into the remote SQLite database.

    The database file (interviews.db) is located in the SSH directory.
    """
    remote_directory, db_path = get_remote_database_location()

    ssh, tmp_key_path = get_ssh_connection()
    try:
        ensure_remote_directory(ssh, remote_directory)
        create_table_query = """
        CREATE TABLE IF NOT EXISTS progress (
            student_id TEXT,
            name TEXT,
            interview_type TEXT,
            completion_timestamp TEXT
        )
        """
        run_remote_sql(ssh, db_path, create_table_query)

        insert_query = """
        INSERT INTO progress (
            student_id,
            name,
            interview_type,
            completion_timestamp
        ) VALUES (?, ?, ?, ?)
        """
        run_remote_sql(
            ssh,
            db_path,
            insert_query,
            [student_id, name, interview_type, timestamp],
        )
    finally:
        close_ssh_connection(ssh, tmp_key_path)


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
    _, db_path = get_remote_database_location()

    ssh, tmp_key_path = get_ssh_connection()
    try:
        existing_columns = run_remote_sql(
            ssh,
            db_path,
            "PRAGMA table_info(interviews)",
            fetch="all",
        ) or []
        existing_column_names = {row[1] for row in existing_columns}
        required_columns = {
            "survey_helpfulness": "TEXT",
            "survey_connection": "TEXT",
            "survey_understanding": "TEXT",
            "survey_validation": "TEXT",
            "survey_feedback": "TEXT",
            "survey_timestamp": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_column_names:
                run_remote_sql(
                    ssh,
                    db_path,
                    f"ALTER TABLE interviews ADD COLUMN {column_name} {column_type}",
                )

        update_query = """
        UPDATE interviews
        SET survey_helpfulness = ?,
            survey_connection = ?,
            survey_understanding = ?,
            survey_validation = ?,
            survey_feedback = ?,
            survey_timestamp = ?
        WHERE interview_id = ?
        """
        run_remote_sql(
            ssh,
            db_path,
            update_query,
            [
                helpfulness_rating,
                connection_rating,
                understanding_rating,
                validation_rating,
                feedback,
                survey_timestamp,
                interview_id,
            ],
        )
    finally:
        close_ssh_connection(ssh, tmp_key_path)
