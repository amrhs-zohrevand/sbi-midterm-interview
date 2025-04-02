import os
import time
import streamlit as st

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Instead of using Google Sheets, this function writes an SQL INSERT statement for the interview
    data into an SQL file located in the SSH database directory.
    """
    # Read the SSH username from secrets
    ssh_username = st.secrets.get("SSH_USERNAME")
    # Build the directory path on the SSH server
    ssh_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    os.makedirs(ssh_directory, exist_ok=True)
    
    sql_file_path = os.path.join(ssh_directory, "interviews.sql")
    
    # Escape single quotes in the transcript to avoid SQL errors
    transcript_escaped = transcript.replace("'", "''")
    
    # Construct the INSERT statement
    sql_statement = (
        "INSERT INTO interviews (interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes) "
        f"VALUES ('{interview_id}', '{student_id}', '{name}', '{company}', '{interview_type}', '{timestamp}', '{transcript_escaped}', '{duration_minutes}');\n"
    )
    
    # Append the SQL statement to the file
    with open(sql_file_path, "a") as f:
        f.write(sql_statement)

def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Instead of updating a Google Sheet, this function writes an SQL INSERT statement for the progress update
    into an SQL file located in the SSH database directory.
    """
    ssh_username = st.secrets.get("SSH_USERNAME")
    ssh_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    os.makedirs(ssh_directory, exist_ok=True)
    
    sql_file_path = os.path.join(ssh_directory, "progress.sql")
    
    sql_statement = (
        "INSERT INTO progress (student_id, name, interview_type, completion_timestamp) "
        f"VALUES ('{student_id}', '{name}', '{interview_type}', '{timestamp}');\n"
    )
    
    with open(sql_file_path, "a") as f:
        f.write(sql_statement)
