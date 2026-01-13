import os
import time
import sqlite3
import streamlit as st
from ssh_utils import get_ssh_connection, ensure_remote_directory


def run_remote_sql(ssh, db_path, sql_query):
    """
    Executes *sql_query* on the remote SQLite database at *db_path*.

    Strategy:
    1. First try the fast path using the `sqlite3` command‑line binary.
    2. If that binary is unavailable (e.g. recently removed from the server),
       transparently fall back to a Python one‑liner executed remotely. Most
       servers have Python even when the CLI tool is absent.
    3. In both cases any stderr output is considered an error and surfaced to
       the caller so that higher‑level functions (e.g. `save_interview_to_sheet`)
       can fail fast.
    """
    # ------------------------------------------------------------------
    # Fast path – sqlite3 CLI
    # ------------------------------------------------------------------
    safe_query_cli = sql_query.replace('"', '\\"')  # escape for CLI quoting
    cli_cmd = f"sqlite3 {db_path} \"{safe_query_cli}\""
    stdin, stdout, stderr = ssh.exec_command(cli_cmd)
    err = stderr.read().decode().strip()

    # If the binary is missing, stderr usually contains "command not found".
    if err and "command not found" in err.lower():
        # ------------------------------------------------------------------
        # Fallback path – Python stdlib on the remote host
        # ------------------------------------------------------------------
        # Triple‑quote the SQL and escape existing triple single‑quotes.
        safe_query_py = sql_query.replace("'''", "''")
        python_script = f"""
import sqlite3, textwrap

DB_PATH = r'''{db_path}'''
SQL = textwrap.dedent(r'''{safe_query_py}''')

conn = sqlite3.connect(DB_PATH)
conn.executescript(SQL)
conn.commit()
conn.close()
"""
        # Heredoc prevents quoting issues.
        python_cmd = f"python3 - <<'PY'\n{python_script}\nPY"
        stdin2, stdout2, stderr2 = ssh.exec_command(python_cmd)
        err2 = stderr2.read().decode().strip()
        if err2:
            raise Exception(f"SQLite error (python fallback): {err2}")
    elif err:
        # sqlite3 CLI was available but returned an error – propagate.
        raise Exception(f"SQLite error: {err}")


def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Inserts the interview data into the remote SQLite database.
    The database file (interviews.db) is located in the SSH directory.
    
    Args:
        interview_id: Unique identifier for this interview session
        student_id: Student identifier
        name: Student/respondent name
        company: Company name (may be empty string)
        interview_type: Type of interview being conducted
        timestamp: Timestamp of interview completion
        transcript: Full text transcript of the interview
        duration_minutes: Interview duration in minutes as string
        
    Raises:
        ValueError: If required secrets are not configured
        Exception: If SSH connection or database operation fails
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"

    ssh = None
    tmp_key_path = None
    try:
        ssh, tmp_key_path = get_ssh_connection()
        
        # Ensure the remote directory exists
        ensure_remote_directory(ssh, remote_directory)

        # Create the interviews table if it doesn't exist
        create_table_query = (
            "CREATE TABLE IF NOT EXISTS interviews ("
            "interview_id TEXT, "
            "student_id TEXT, "
            "name TEXT, "
            "company TEXT, "
            "interview_type TEXT, "
            "timestamp TEXT, "
            "transcript TEXT, "
            "duration_minutes TEXT, "
            "summary TEXT);"
        )
        run_remote_sql(ssh, db_path, create_table_query)

        # Escape single quotes in transcript to avoid SQL issues
        transcript_escaped = transcript.replace("'", "''")
        insert_query = (
            "INSERT INTO interviews (interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes) "
            f"VALUES ('{interview_id}', '{student_id}', '{name}', '{company}', '{interview_type}', '{timestamp}', '{transcript_escaped}', '{duration_minutes}');"
        )
        run_remote_sql(ssh, db_path, insert_query)
    except Exception as e:
        st.error(f"Failed to save interview to database: {str(e)}")
        raise
    finally:
        if ssh:
            ssh.close()
        if tmp_key_path and os.path.exists(tmp_key_path):
            os.remove(tmp_key_path)


def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Inserts a progress update into the remote SQLite database.
    The database file (interviews.db) is located in the SSH directory.
    
    Args:
        student_id: Student identifier
        name: Student name
        interview_type: Type of interview completed
        timestamp: Completion timestamp
        
    Raises:
        ValueError: If required secrets are not configured
        Exception: If SSH connection or database operation fails
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"

    ssh = None
    tmp_key_path = None
    try:
        ssh, tmp_key_path = get_ssh_connection()
        ensure_remote_directory(ssh, remote_directory)

        # Create the progress table if it doesn't exist
        create_table_query = (
            "CREATE TABLE IF NOT EXISTS progress ("
            "student_id TEXT, "
            "name TEXT, "
            "interview_type TEXT, "
            "completion_timestamp TEXT);"
        )
        run_remote_sql(ssh, db_path, create_table_query)

        insert_query = (
            "INSERT INTO progress (student_id, name, interview_type, completion_timestamp) "
            f"VALUES ('{student_id}', '{name}', '{interview_type}', '{timestamp}');"
        )
        run_remote_sql(ssh, db_path, insert_query)
    except Exception as e:
        st.error(f"Failed to update progress sheet: {str(e)}")
        raise
    finally:
        if ssh:
            ssh.close()
        if tmp_key_path and os.path.exists(tmp_key_path):
            os.remove(tmp_key_path)


def get_transcript_by_student_and_type(student_id, interview_type, ssh_conn=None):
    """
    Retrieves the most recent transcript for a given student and interview type from the remote SQLite database.
    
    Args:
        student_id: Student identifier
        interview_type: Type of interview to retrieve
        ssh_conn: Optional existing SSH connection to reuse
        
    Returns:
        str: The transcript summary text, or an empty string if not found
        
    Raises:
        ValueError: If required secrets are not configured
        Exception: If SSH connection or database query fails
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"

    # Use the provided SSH connection if available, otherwise establish a new one.
    remove_after = False
    tmp_key_path = None
    if ssh_conn is None:
        ssh, tmp_key_path = get_ssh_connection()
        remove_after = True
    else:
        ssh = ssh_conn

    try:
        query = (
            f"SELECT summary FROM interviews "
            f"WHERE student_id='{student_id}' AND interview_type='{interview_type}' "
            f"ORDER BY timestamp DESC LIMIT 1;"
        )
        run_remote_sql(ssh, db_path, query)
        # We have to capture the result manually because run_remote_sql doesn't return stdout.
        # Let's execute a select through the Python fallback directly to fetch the summary.
        python_fetch = f"""
import sqlite3, json
conn = sqlite3.connect(r'{db_path}')
cur = conn.cursor()
cur.execute(\"{query}\")
row = cur.fetchone()
print(json.dumps(row[0] if row else ''))
conn.close()
"""
        python_cmd = f"python3 - <<'PY'\n{python_fetch}\nPY"
        stdin, stdout, stderr = ssh.exec_command(python_cmd)
        result = stdout.read().decode().strip().strip('"')  # simple JSON string value
        error = stderr.read().decode().strip()
        if error:
            raise Exception(f"SQLite error while fetching transcript: {error}")
        return result
    except Exception as e:
        st.error(f"Failed to retrieve transcript: {str(e)}")
        return ""  # Return empty string on error to allow interview to proceed
    finally:
        if remove_after and ssh:
            ssh.close()
        if tmp_key_path and os.path.exists(tmp_key_path):
            os.remove(tmp_key_path)


def update_interview_summary(interview_id, summary):
    """
    Updates the interview record identified by interview_id with the given summary.
    
    Args:
        interview_id: Unique identifier for the interview session
        summary: Summary text to store
        
    Raises:
        ValueError: If required secrets are not configured
        Exception: If SSH connection or database update fails
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"

    ssh = None
    tmp_key_path = None
    try:
        ssh, tmp_key_path = get_ssh_connection()
        summary_escaped = summary.replace("'", "''")
        update_query = (
            f"UPDATE interviews SET summary = '{summary_escaped}' WHERE interview_id = '{interview_id}';"
        )
        run_remote_sql(ssh, db_path, update_query)
    except Exception as e:
        st.error(f"Failed to update interview summary: {str(e)}")
        raise
    finally:
        if ssh:
            ssh.close()
        if tmp_key_path and os.path.exists(tmp_key_path):
            os.remove(tmp_key_path)
