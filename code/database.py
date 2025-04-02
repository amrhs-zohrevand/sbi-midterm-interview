import os
import time
import streamlit as st

def get_ssh_directory():
    # Read the SSH username from st.secrets; adjust the key if needed.
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("SSH_USERNAME is not defined in secrets. Please set it in your secrets file.")
    # Build the directory path on the SSH server
    ssh_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    return ssh_directory

def ensure_ssh_directory(ssh_directory):
    try:
        os.makedirs(ssh_directory, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied while creating directory {ssh_directory}. "
            "Ensure the current process has write access to this directory. "
            f"Original error: {e}"
        )

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Writes an SQL INSERT statement for the interview data into an SQL file located in the SSH directory.
    """
    ssh_directory = get_ssh_directory()
    ensure_ssh_directory(ssh_directory)
    
    sql_file_path = os.path.join(ssh_directory, "interviews.sql")
    
    # Escape single quotes in the transcript to avoid SQL syntax errors
    transcript_escaped = transcript.replace("'", "''")
    
    sql_statement = (
        "INSERT INTO interviews (interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes) "
        f"VALUES ('{interview_id}', '{student_id}', '{name}', '{company}', '{interview_type}', '{timestamp}', '{transcript_escaped}', '{duration_minutes}');\n"
    )
    
    with open(sql_file_path, "a") as f:
        f.write(sql_statement)

def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Writes an SQL INSERT statement for the progress update into an SQL file located in the SSH directory.
    """
    ssh_directory = get_ssh_directory()
    ensure_ssh_directory(ssh_directory)
    
    sql_file_path = os.path.join(ssh_directory, "progress.sql")
    
    sql_statement = (
        "INSERT INTO progress (student_id, name, interview_type, completion_timestamp) "
        f"VALUES ('{student_id}', '{name}', '{interview_type}', '{timestamp}');\n"
    )
    
    with open(sql_file_path, "a") as f:
        f.write(sql_statement)
