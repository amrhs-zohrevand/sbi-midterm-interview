import streamlit as st
import hmac
import time
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
import paramiko
import io
import tempfile


def check_if_interview_completed(directory, username):
    """Check if interview transcript/time file exists which signals that interview was completed."""

    # Test account has multiple interview attempts
    if username != "testaccount":

        # Check if file exists
        try:
            with open(os.path.join(directory, f"{username}.txt"), "r") as _:
                return True

        except FileNotFoundError:
            return False

    else:

        return False


def save_interview_data(folder_id, student_number, company_name, transcripts_directory=None, times_directory=None):
    # Use default directories from config if not provided
    if transcripts_directory is None or times_directory is None:
        import config
        if transcripts_directory is None:
            transcripts_directory = config.TRANSCRIPTS_DIRECTORY
        if times_directory is None:
            times_directory = config.TIMES_DIRECTORY

    # Get current date in YYMMDD format
    current_date = time.strftime("%y%m%d")

    # Sanitize company name to remove spaces and special characters
    sanitized_company = "".join(c for c in company_name if c.isalnum())

    # Construct the file names
    transcript_filename = f"{current_date}_{student_number}_{sanitized_company}_transcript.txt"
    time_filename = f"{current_date}_{student_number}_{sanitized_company}_time.txt"

    # Ensure directories exist (if you want temporary local storage for uploading)
    os.makedirs(transcripts_directory, exist_ok=True)
    os.makedirs(times_directory, exist_ok=True)

    # Define file paths
    transcript_file = os.path.join(transcripts_directory, transcript_filename)
    time_file = os.path.join(times_directory, time_filename)

    # Save transcript
    with open(transcript_file, "w") as t:
        t.write(f"Session ID: {st.session_state.session_id}\n\n")
        for message in st.session_state.messages[1:]:
            t.write(f"{message['role']}: {message['content']}\n")

    # Save interview timing data
    with open(time_file, "w") as d:
        duration = (time.time() - st.session_state.start_time) / 60
        d.write(
            f"Session ID: {st.session_state.session_id}\n"
            f"Start time (UTC): {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )

    # Upload files to Google Drive
    transcript_link = upload_to_google_drive(transcript_file, transcript_filename, folder_id)
    time_link = upload_to_google_drive(time_file, time_filename, folder_id)

    # Return both the transcript sharing link and the local file path for attachment
    return transcript_link, transcript_file
        
def upload_to_google_drive(file_path, file_name, folder_id):
    """Uploads a file to Google Drive, overwriting an existing one if found."""

    # Retrieve and parse the JSON from Streamlit secrets
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])

    # Ensure the private_key is correctly formatted
    if "\\n" in service_account_info["private_key"]:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

    # Authenticate with Google Drive
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    service = build("drive", "v3", credentials=credentials)

    # Step 1: Search for existing file in the folder
    query = f"'{folder_id}' in parents and name='{file_name}' and trashed=false"
    response = service.files().list(q=query, fields="files(id, webViewLink)").execute()
    files = response.get("files", [])

    if files:
        # If file exists, update it instead of re-uploading
        existing_file_id = files[0]["id"]
        media = MediaFileUpload(file_path, mimetype="text/plain", resumable=True)

        updated_file = service.files().update(
            fileId=existing_file_id,
            media_body=media
        ).execute()

        # Ensure the file has public sharing permissions
        service.permissions().create(
            fileId=existing_file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()

        # Fetch the updated sharing link
        file_info = service.files().get(fileId=existing_file_id, fields="webViewLink").execute()
        return file_info.get("webViewLink")

    else:
        # If file does not exist, upload a new one
        file_metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype="text/plain")

        new_file = service.files().create(
            body=file_metadata, media_body=media, fields="id, webViewLink"
        ).execute()

        # Ensure the new file has public sharing permissions
        service.permissions().create(
            fileId=new_file["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()

        return new_file.get("webViewLink") # Return the file sharing link


def send_transcript_email(student_number, recipient_email, transcript_link, transcript_file):
    """
    Sends the interview transcript via either Gmail or LIACS SMTP depending on config.
    """
    import base64
    import paramiko
    import streamlit as st
    import tempfile
    import os
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    use_liacs = st.secrets.get("USE_LIACS_EMAIL", False)

    from_addr = "bs-internships@liacs.leidenuniv.nl"
    to_addr = f"{student_number}@vuw.leidenuniv.nl"
    cc_addr = recipient_email

    subject = "Your Interview Transcript from Leiden University"
    body = f"""\
Dear Student,

Thank you for participating in the interview. Your transcript has been saved.

You can download your transcript here:
{transcript_link}

Best regards,
Leiden University Interview System
"""

    # Force a fallback name if os.path.basename returns an empty string
    fallback_name = "transcript.txt"
    file_name = os.path.basename(transcript_file) or fallback_name

    if use_liacs:
        # LIACS branch
        with open(transcript_file, "rb") as f:
            attachment_data = base64.b64encode(f.read()).decode()

        # Build the Python code to run remotely
        python_code = f"""\
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

msg = MIMEMultipart()
msg['Subject'] = {repr(subject)}
msg['From'] = {repr(from_addr)}
msg['To'] = {repr(to_addr)}
msg['Cc'] = {repr(cc_addr)}

body = {repr(body)}
msg.attach(MIMEText(body, 'plain'))

attachment_data = base64.b64decode({repr(attachment_data)})
part = MIMEBase("text", "plain")
part.set_payload(attachment_data)
encoders.encode_base64(part)

# Force a fallback name if needed
filename = {repr(file_name)}
if not filename:
    filename = "transcript.txt"

part.add_header("Content-Type", f'text/plain; name="{filename}"')
part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
msg.attach(part)

with smtplib.SMTP('smtp.leidenuniv.nl') as server:
    server.send_message(msg)

print("✅ Remote email sent.")
"""
        python_code = python_code.strip()
        encoded_code = base64.b64encode(python_code.encode()).decode()

        try:
            ssh_host = "ssh.liacs.nl"
            ssh_username = st.secrets["LIACS_SSH_USERNAME"]

            key_str = st.secrets["LIACS_SSH_KEY"]
            if "\\n" in key_str:
                key_str = key_str.replace("\\n", "\n")
            if key_str.startswith("-----BEGIN OPENSSH PRIVATE KEY-----") and "-----END OPENSSH PRIVATE KEY-----" in key_str:
                header = "-----BEGIN OPENSSH PRIVATE KEY-----"
                footer = "-----END OPENSSH PRIVATE KEY-----"
                key_body = key_str[len(header):-len(footer)].strip()
                lines = [key_body[i:i+70] for i in range(0, len(key_body), 70)]
                key_str = header + "\n" + "\n".join(lines) + "\n" + footer

            with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp_key_file:
                tmp_key_file.write(key_str)
                tmp_key_path = tmp_key_file.name

            try:
                from paramiko import Ed25519Key
                key = Ed25519Key.from_private_key_file(tmp_key_path)
            except paramiko.SSHException:
                from paramiko import RSAKey
                key = RSAKey.from_private_key_file(tmp_key_path)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ssh_host, username=ssh_username, pkey=key)

            remote_cmd = f'printf "%s" "{encoded_code}" | base64 -d | python3'
            stdin, stdout, stderr = ssh.exec_command(remote_cmd)

            output = stdout.read().decode()
            error = stderr.read().decode()

            if error:
                st.error(f"⚠️ Remote error:\n{error}")
            else:
                st.success(output.strip())

            ssh.close()
            os.remove(tmp_key_path)

        except Exception as e:
            st.error("❌ Failed to send email via LIACS SMTP.")
            st.exception(e)

    else:
        # Gmail branch
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = "businessinternship.liacs@gmail.com"
        sender_password = st.secrets["EMAIL_PASSWORD"]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_addr
        msg["Cc"] = cc_addr
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        # Read file and attach as text/plain
        with open(transcript_file, "rb") as f:
            content = f.read()

        part = MIMEBase("text", "plain")
        part.set_payload(content)
        encoders.encode_base64(part)

        # Force a fallback name if needed
        if not file_name:
            file_name = "transcript.txt"

        part.add_header("Content-Type", f'text/plain; name="{file_name}"')
        part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')
        msg.attach(part)

        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, sender_password)

            recipients = [to_addr, cc_addr]
            server.sendmail(sender_email, recipients, msg.as_string())
            server.quit()

            st.success(f"📬 Email sent to {recipients}")
        except Exception as e:
            st.error("Error sending email via Gmail SMTP.")
            st.exception(e)


#





