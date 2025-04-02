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
    Returns the SSH client, SFTP client, and the temporary key file path.
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
        sftp = ssh.open_sftp()
        return ssh, sftp, tmp_key_path
    except Exception as e:
        os.remove(tmp_key_path)
        raise e

def remote_mkdir(sftp, remote_directory):
    """
    Recursively create remote directories if they do not exist.
    """
    dirs = remote_directory.split('/')
    path = ""
    for dir in dirs:
        if dir:
            path = path + "/" + dir
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes):
    """
    Writes an SQL INSERT statement for the interview data into the remote file
    'interviews.sql' located in the SSH directory (/home/{LIACS_SSH_USERNAME}/BS-Interviews/Database).
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    
    ssh, sftp, tmp_key_path = get_ssh_connection()
    try:
        remote_mkdir(sftp, remote_directory)
        sql_file_path = remote_directory + "/interviews.sql"
        transcript_escaped = transcript.replace("'", "''")
        sql_statement = (
            "INSERT INTO interviews (interview_id, student_id, name, company, interview_type, timestamp, transcript, duration_minutes) "
            f"VALUES ('{interview_id}', '{student_id}', '{name}', '{company}', '{interview_type}', '{timestamp}', '{transcript_escaped}', '{duration_minutes}');\n"
        )
        try:
            remote_file = sftp.open(sql_file_path, "a")
        except IOError:
            remote_file = sftp.open(sql_file_path, "w")
        remote_file.write(sql_statement)
        remote_file.flush()
        remote_file.close()
    finally:
        sftp.close()
        ssh.close()
        os.remove(tmp_key_path)

def update_progress_sheet(student_id, name, interview_type, timestamp):
    """
    Writes an SQL INSERT statement for the progress update into the remote file
    'progress.sql' located in the SSH directory (/home/{LIACS_SSH_USERNAME}/BS-Interviews/Database).
    """
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets.")
    remote_directory = f"/home/{ssh_username}/BS-Interviews/Database"
    
    ssh, sftp, tmp_key_path = get_ssh_connection()
    try:
        remote_mkdir(sftp, remote_directory)
        sql_file_path = remote_directory + "/progress.sql"
        sql_statement = (
            "INSERT INTO progress (student_id, name, interview_type, completion_timestamp) "
            f"VALUES ('{student_id}', '{name}', '{interview_type}', '{timestamp}');\n"
        )
        try:
            remote_file = sftp.open(sql_file_path, "a")
        except IOError:
            remote_file = sftp.open(sql_file_path, "w")
        remote_file.write(sql_statement)
        remote_file.flush()
        remote_file.close()
    finally:
        sftp.close()
        ssh.close()
        os.remove(tmp_key_path)
