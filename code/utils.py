import streamlit as st
import hmac
import time
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
import paramiko
import io
import tempfile
# ▸ NEW: reuse the SSH helpers that already exist in database.py
from database import get_ssh_connection, ensure_remote_directory

# ─────────────────────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def _upload_to_remote_database_folder(local_path: str, subfolder: str = "Transcripts"):
    """
    Copy *local_path* to /home/<user>/BS-Interviews/Database/<subfolder>/ on the
    LIACS server.  Called only when the toggle
    `SAVE_TRANSCRIPT_TO_DB_FOLDER` (boolean) is **true** in secrets.

    Any exception is swallowed after logging a Streamlit warning so that the
    main flow never breaks if the SCP fails.
    """
    try:
        ssh, tmp_key_path = get_ssh_connection()          # existing helper
        ssh_username = st.secrets["LIACS_SSH_USERNAME"]   # guaranteed by helper
        remote_dir   = f"/home/{ssh_username}/BS-Interviews/Database/{subfolder}"
        ensure_remote_directory(ssh, remote_dir)          # idempotent

        sftp = ssh.open_sftp()
        remote_path = f"{remote_dir}/{os.path.basename(local_path)}"
        sftp.put(local_path, remote_path)
        sftp.close()
        ssh.close()
    except Exception as e:
        st.warning(f"⚠️ Could not upload transcript to remote folder: {e}")
    finally:
        # get_ssh_connection creates a temporary key file; best-effort cleanup
        try:
            os.remove(tmp_key_path)
        except Exception:
            pass


def check_if_interview_completed(directory, username):
    """Check if interview transcript/time file exists which signals that interview was completed."""
    if username != "testaccount":
        try:
            with open(os.path.join(directory, f"{username}.txt"), "r"):
                return True
        except FileNotFoundError:
            return False
    return False


def save_interview_data(
    student_number,
    company_name,
    transcripts_directory=None,
    times_directory=None,
):
    """
    Creates/updates two local files (transcript + timing) **and, optionally,
    uploads the transcript** to the remote *Database/Transcripts* folder when
    `SAVE_TRANSCRIPT_TO_DB_FOLDER` is True in Streamlit secrets.
    """
    # Use default directories from config if not provided
    if transcripts_directory is None or times_directory is None:
        import config

        transcripts_directory = transcripts_directory or config.TRANSCRIPTS_DIRECTORY
        times_directory       = times_directory       or config.TIMES_DIRECTORY

    current_date      = time.strftime("%y%m%d")
    sanitized_company = "".join(c for c in company_name if c.isalnum())

    transcript_filename = (
        f"{current_date}_{student_number}_{sanitized_company}_transcript.txt"
    )
    time_filename       = (
        f"{current_date}_{student_number}_{sanitized_company}_time.txt"
    )

    os.makedirs(transcripts_directory, exist_ok=True)
    os.makedirs(times_directory,       exist_ok=True)

    transcript_file = os.path.join(transcripts_directory, transcript_filename)
    time_file       = os.path.join(times_directory,       time_filename)

    # ── write transcript ───────────────────────────────────────────────────
    with open(transcript_file, "w", encoding="utf-8") as t:
        t.write(f"Session ID: {st.session_state.session_id}\n\n")
        for message in st.session_state.messages[1:]:
            t.write(f"{message['role']}: {message['content']}\n")

    # ── write timing – kept unchanged ──────────────────────────────────────
    duration = (time.time() - st.session_state.start_time) / 60
    with open(time_file, "w", encoding="utf-8") as d:
        d.write(
            f"Session ID: {st.session_state.session_id}\n"
            f"Start time (UTC): "
            f"{time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )

    # ▸ NEW: optional remote upload ----------------------------------------
    if st.secrets.get("SAVE_TRANSCRIPT_TO_DB_FOLDER", False):
        _upload_to_remote_database_folder(transcript_file, subfolder="Transcripts")

    # Google-Drive upload was removed earlier – leave link blank
    transcript_link = ""
    return transcript_link, transcript_file

def send_transcript_email(
    student_number,
    recipient_email,
    transcript_link,
    transcript_file,
    name_from_form=None  # NEW parameter to pass the interviewee's name
):
    """
    Sends the interview transcript via either Gmail or LIACS SMTP depending on config.
    """
    use_liacs = st.secrets.get("USE_LIACS_EMAIL", False)

    from_addr = "bs-internships@liacs.leidenuniv.nl"
    
    # Example: sending to both the student's institutional address & the "recipient_email"
    student_number = (student_number or "").strip()

    if student_number:
        to_addr = f"{student_number}@vuw.leidenuniv.nl"
        cc_addr = recipient_email.strip()
    else:
        to_addr = recipient_email.strip()
        cc_addr = ""
        
    bcc_addr = "zohrehvanda@liacs.leidenuniv.nl"

    subject = "Your Interview Transcript from Leiden University"
    
    # Decide how to greet the recipient
    if name_from_form and name_from_form.strip():
        greeting_name = name_from_form.strip()
    else:
        greeting_name = "participant"

    # Updated email body:
    body = f"""\
This is an automated email, please do not reply.

Dear {greeting_name},

Thank you for participating in the interview. Your transcript has been saved and is attached to this email.

Best wishes,
Business Studies Internship Team
LIACS, Leiden University
"""

    fallback_name = "transcript.txt"
    file_name = os.path.basename(transcript_file) or fallback_name
    if not file_name:
        file_name = fallback_name

    if use_liacs:
        with open(transcript_file, "rb") as f:
            attachment_data = base64.b64encode(f.read()).decode()
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
msg['Bcc'] = {repr(bcc_addr)}

body = {repr(body)}
msg.attach(MIMEText(body, 'plain'))

attachment_data = base64.b64decode({repr(attachment_data)})
part = MIMEBase("text", "plain")
part.set_payload(attachment_data)
encoders.encode_base64(part)
part.add_header("Content-Type", f'text/plain; name="{file_name}"')
part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')
msg.attach(part)

with smtplib.SMTP('smtp.leidenuniv.nl') as server:
    server.send_message(msg)

print("✅ Email sent. Please wait with closing this window as we are still processing data.")
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
        with open(transcript_file, "rb") as f:
            content = f.read()
        part = MIMEBase("text", "plain")
        part.set_payload(content)
        encoders.encode_base64(part)
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
