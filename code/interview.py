import os
import streamlit as st
import paramiko
import tempfile

def get_sftp_client():
    """
    Connects to the SSH server using credentials from st.secrets and returns the SSH client,
    SFTP client, and temporary key file path.
    """
    ssh_host = "ssh.liacs.nl"
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets. Please set it in your secrets file.")

    key_str = st.secrets.get("LIACS_SSH_KEY")
    if not key_str:
        raise ValueError("LIACS_SSH_KEY is not defined in secrets. Please set it in your secrets file.")

    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")

    # Write key to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp_key_file:
        tmp_key_file.write(key_str)
        tmp_key_path = tmp_key_file.name

    # Try to load the key (try Ed25519 first, then RSA)
    try:
        from paramiko import Ed25519Key
        key = Ed25519Key.from_private_key_file(tmp_key_path)
    except paramiko.SSHException:
        from paramiko import RSAKey
        key = RSAKey.from_private_key_file(tmp_key_path)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ssh_host, username=ssh_username, pkey=key)
    sftp = ssh.open_sftp()
    return ssh, sftp, tmp_key_path

def ensure_remote_directory(sftp, remote_directory):
    """
    Checks if the remote directory exists and creates it if it does not.
    """
    try:
        sftp.stat(remote_directory)
    except IOError:
        # Directory does not exist so create it
        sftp.mkdir(remote_directory)

def write_remote_file(sftp, remote_path, data):
    """
    Opens the remote file in append mode (or creates it if it doesn't exist) and writes data.
    """
    try:
        remote_file = sftp.file(remote_path, mode='a')
    except IOError:
        remote_file = sftp.file(remote_path, mode='w')
    remote_file.write(data)
    remote_file.flush()
    remote_file.close()

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Writes an SQL INSERT statement for the interview data into a remote SQL file located in the SSH directory.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    
    ssh, sftp, tmp_key_path = get_sftp_client()
    try:
        ensure_remote_directory(sftp, remote_directory)
        remote_file_path = os.path.join(remote_directory, "interviews.sql")
        
        # Escape single quotes in transcript to avoid SQL syntax errors
        transcript_escaped = transcript.replace("'", "''")
        sql_statement = (
            "INSERT INTO interviews (interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes) "
            f"VALUES ('{interview_id}', '{student_id}', '{name}', '{company}', '{interview_type}', '{timestamp}', '{transcript_escaped}', '{duration_minutes}');\n"
        )
        write_remote_file(sftp, remote_file_path, sql_statement)
    finally:
        sftp.close()
        ssh.close()
        os.remove(tmp_key_path)

def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Writes an SQL INSERT statement for the progress update into a remote SQL file located in the SSH directory.
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    
    ssh, sftp, tmp_key_path = get_sftp_client()
    try:
        ensure_remote_directory(sftp, remote_directory)
        remote_file_path = os.path.join(remote_directory, "progress.sql")
        
        sql_statement = (
            "INSERT INTO progress (student_id, name, interview_type, completion_timestamp) "
            f"VALUES ('{student_id}', '{name}', '{interview_type}', '{timestamp}');\n"
        )
        write_remote_file(sftp, remote_file_path, sql_statement)
    finally:
        sftp.close()
        ssh.close()
        os.remove(tmp_key_path)
