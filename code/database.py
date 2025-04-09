import os
import time
import streamlit as st
import paramiko
import tempfile

def format_private_key(key_str):
    """
    Normalize the private key string as done in the email sending code.
    """
    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")
    if key_str.startswith("-----BEGIN OPENSSH PRIVATE KEY-----") and "-----END OPENSSH PRIVATE KEY-----" in key_str:
        header = "-----BEGIN OPENSSH PRIVATE KEY-----"
        footer = "-----END OPENSSH PRIVATE KEY-----"
        key_body = key_str[len(header):-len(footer)].strip()
        lines = [key_body[i:i+70] for i in range(0, len(key_body), 70)]
        key_str = header + "\n" + "\n".join(lines) + "\n" + footer
    return key_str

def get_ssh_connection():
    """
    Establish an SSH connection using the LIACS SSH credentials.
    Returns the SSH client and the temporary key file path.
    """
    ssh_host = "ssh.liacs.nl"
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets. Please set it in your secrets file.")
    
    key_str = st.secrets.get("LIACS_SSH_KEY")
    if not key_str:
        raise ValueError("LIACS_SSH_KEY is not defined in secrets. Please set it in your secrets file.")
    key_str = format_private_key(key_str)
    
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp_key_file:
        tmp_key_file.write(key_str)
        tmp_key_path = tmp_key_file.name
    
    try:
        try:
            key = paramiko.Ed25519Key.from_private_key_file(tmp_key_path)
        except paramiko.SSHException:
            key = paramiko.RSAKey.from_private_key_file(tmp_key_path)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ssh_host, username=ssh_username, pkey=key)
        return ssh, tmp_key_path
    except Exception as e:
        os.remove(tmp_key_path)
        raise e

def ensure_remote_directory(ssh, remote_directory):
    """
    Ensures the remote directory exists by executing a mkdir command.
    """
    mkdir_cmd = f"mkdir -p {remote_directory}"
    stdin, stdout, stderr = ssh.exec_command(mkdir_cmd)
    err = stderr.read().decode().strip()
    if err:
        raise PermissionError(f"Failed to create remote directory {remote_directory}: {err}")

def run_remote_sql(ssh, db_path, sql_query):
    """
    Executes the given SQL query on the remote SQLite database using the sqlite3 command.
    Assumes that the sqlite3 command-line tool is available on the remote server.
    """
    # Escape double quotes in the query so it can be wrapped in double quotes.
    safe_query = sql_query.replace('"', '\\"')
    cmd = f'sqlite3 {db_path} "{safe_query}"'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    err = stderr.read().decode().strip()
    if err:
        raise Exception(f"SQLite error: {err}")

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Inserts the interview data into the remote SQLite database.
    The database file (interviews.db) is located in the SSH directory.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"
    
    ssh, tmp_key_path = get_ssh_connection()
    try:
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
    finally:
        ssh.close()
        os.remove(tmp_key_path)

def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Inserts a progress update into the remote SQLite database.
    The database file (interviews.db) is located in the SSH directory.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"
    
    ssh, tmp_key_path = get_ssh_connection()
    try:
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
    finally:
        ssh.close()
        os.remove(tmp_key_path)
        
def get_transcript_by_student_and_type(student_id, interview_type, ssh_conn=None):
    """
    Retrieves the most recent transcript for a given student and interview type from the remote SQLite database.
    Accepts an optional ssh_conn parameter. If not provided, a new connection is established.
    Returns the transcript text, or an empty string if not found.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"
    
    # Use the provided SSH connection if available, otherwise establish a new one.
    remove_after = False
    if ssh_conn is None:
        ssh, tmp_key_path = get_ssh_connection()
        remove_after = True
    else:
        ssh = ssh_conn
        
    try:
        query = (
            f"SELECT transcript FROM interviews "
            f"WHERE student_id='{student_id}' AND interview_type='{interview_type}' "
            f"ORDER BY timestamp DESC LIMIT 1;"
        )
        safe_query = query.replace('"', '\\"')
        cmd = f'sqlite3 {db_path} "{safe_query}"'
        stdin, stdout, stderr = ssh.exec_command(cmd)
        result = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        if error:
            raise Exception(f"SQLite error: {error}")
        return result
    finally:
        if remove_after:
            ssh.close()

def update_interview_summary(interview_id, summary):
    """
    Updates the interview record identified by interview_id with the given summary.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    db_path = f"{remote_directory}/interviews.db"

    ssh, tmp_key_path = get_ssh_connection()
    try:
        summary_escaped = summary.replace("'", "''")
        update_query = (
            f"UPDATE interviews SET summary = '{summary_escaped}' WHERE interview_id = '{interview_id}';"
        )
        run_remote_sql(ssh, db_path, update_query)
    finally:
        ssh.close()
        os.remove(tmp_key_path)