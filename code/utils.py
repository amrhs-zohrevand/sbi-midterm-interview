import streamlit as st
import hmac
import time
import os
import json
import smtplib
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
import paramiko
import io
import tempfile
from ssh_utils import format_private_key

def check_if_interview_completed(directory, username):
    """
    Check if interview transcript/time file exists which signals that interview was completed.
    
    Args:
        directory: Directory to check for completion files
        username: Username to check completion status for
        
    Returns:
        bool: True if interview completed, False otherwise
    """
    if username != "testaccount":
        try:
            with open(os.path.join(directory, f"{username}.txt"), "r") as _:
                return True
        except FileNotFoundError:
            return False
    else:
        return False

def save_interview_data(student_number, company_name="", transcripts_directory=None, times_directory=None):
    """
    Persist transcript & timing information to local files.
    
    Args:
        student_number: Student identifier (may be empty string)
        company_name: Company name (optional, defaults to empty string)
        transcripts_directory: Directory to save transcripts (uses config default if None)
        times_directory: Directory to save timing data (uses config default if None)
        
    Returns:
        tuple: (transcript_link, transcript_file) where transcript_link is empty string 
               (no longer uploading to Google Drive) and transcript_file is the local file path
               
    Raises:
        IOError: If file writing fails
    """
    # Use default directories from config if not provided
    if transcripts_directory is None or times_directory is None:
        import config
        if transcripts_directory is None:
            transcripts_directory = config.TRANSCRIPTS_DIRECTORY
        if times_directory is None:
            times_directory = config.TIMES_DIRECTORY

    current_date = time.strftime("%y%m%d")
    sanitized_company = "".join(c for c in company_name if c.isalnum()) if company_name else ""

    # Build filenames – add the company part only when present
    if sanitized_company:
        transcript_filename = f"{current_date}_{student_number}_{sanitized_company}_transcript.txt"
        time_filename       = f"{current_date}_{student_number}_{sanitized_company}_time.txt"
    else:
        transcript_filename = f"{current_date}_{student_number}_transcript.txt"
        time_filename       = f"{current_date}_{student_number}_time.txt"

    os.makedirs(transcripts_directory, exist_ok=True)
    os.makedirs(times_directory,     exist_ok=True)
    transcript_file = os.path.join(transcripts_directory, transcript_filename)
    time_file       = os.path.join(times_directory,       time_filename)

    with open(transcript_file, "w") as t:
        t.write(f"Session ID: {st.session_state.session_id}\n\n")
        for message in st.session_state.messages[1:]:
            t.write(f"{message['role']}: {message['content']}\n")

    with open(time_file, "w") as d:
        duration = (time.time() - st.session_state.start_time) / 60
        d.write(
            f"Session ID: {st.session_state.session_id}\n"
            f"Start time (UTC): {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )

    # Removed Google Drive upload; transcript_link is now set to an empty string.
    transcript_link = ""
    return transcript_link, transcript_file

def _extract_audio_from_response(response_obj):
    """
    Extract audio bytes and mime type from DeepInfra TTS responses.
    """
    if isinstance(response_obj, dict):
        # URL-based fields
        for key in ("audio_url", "audio", "url", "output_url"):
            value = response_obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return _fetch_audio_url(value)
        # Audio dicts with data + mime/content type
        for key in ("audio", "audio_data", "data", "output"):
            value = response_obj.get(key)
            if isinstance(value, dict):
                mime_type = value.get("mime_type") or value.get("content_type") or ""
                for data_key in ("data", "base64", "audio_base64", "wav_base64", "mp3_base64"):
                    data_val = value.get(data_key)
                    if isinstance(data_val, str):
                        try:
                            audio_bytes = base64.b64decode(data_val)
                        except Exception:
                            continue
                        return audio_bytes, mime_type or "audio/wav"
        # Base64-based fields
        for key in ("wav_base64", "audio_base64", "mp3_base64", "base64", "audio"):
            value = response_obj.get(key)
            if isinstance(value, str) and not value.startswith("http"):
                try:
                    audio_bytes = base64.b64decode(value)
                except Exception:
                    continue
                return audio_bytes, "audio/wav"
        # Nested structures
        for key in ("data", "result", "results", "output"):
            value = response_obj.get(key)
            extracted = _extract_audio_from_response(value)
            if extracted:
                return extracted
    elif isinstance(response_obj, list):
        for item in response_obj:
            extracted = _extract_audio_from_response(item)
            if extracted:
                return extracted
    return None

def _fetch_audio_url(url):
    with urllib.request.urlopen(url, timeout=60) as resp:
        audio_bytes = resp.read()
        mime_type = resp.headers.get("Content-Type", "")
    if not mime_type:
        mime_type = "audio/mpeg" if url.lower().endswith(".mp3") else "audio/wav"
    return audio_bytes, mime_type

def synthesize_speech_deepinfra(text, model="hexgrad/Kokoro-82M", api_key=None, timeout=60):
    """
    Synthesize speech using DeepInfra TTS models.
    Returns (audio_bytes, mime_type).
    """
    if not api_key:
        raise ValueError("Missing DEEPINFRA_API_KEY for speech synthesis.")
    # Most DeepInfra TTS models expect "text" (some accept "input").
    payload = {"text": text}
    voice = st.secrets.get("TTS_VOICE", "")
    if voice:
        payload["voice"] = voice
    data = json.dumps(payload).encode("utf-8")
    url = f"https://api.deepinfra.com/v1/inference/{model}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"DeepInfra TTS error: {e.code} {detail}") from e
    if content_type.startswith("audio/"):
        return body, content_type
    if content_type == "application/octet-stream":
        return body, "audio/wav"
    try:
        response_obj = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError("Unexpected DeepInfra TTS response format.") from e
    extracted = _extract_audio_from_response(response_obj)
    if not extracted:
        raise RuntimeError(f"DeepInfra TTS response missing audio data. Response: {response_obj}")
    return extracted

def send_transcript_email(
    student_number,
    recipient_email,
    transcript_link,
    transcript_file,
    name_from_form=None
):
    """
    Sends the interview transcript via either Gmail or LIACS SMTP depending on config.
    
    Args:
        student_number: Student identifier (may be empty string)
        recipient_email: Email address to send transcript to
        transcript_link: Link to transcript (currently unused, kept for backwards compatibility)
        transcript_file: Path to the transcript file to attach
        name_from_form: Name of the interviewee for personalized greeting
        
    Raises:
        Exception: If email sending fails (caught and displayed to user)
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
        
    bcc_addr = "a.h.zohrehvand@liacs.leidenuniv.nl"

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
            key_str = format_private_key(key_str)
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


def send_verification_code(student_number, code):
    """
    Send a short verification code to the student's institutional email.
    
    Args:
        student_number: Student identifier (used to construct email address)
        code: The verification code to send
        
    Raises:
        Exception: If email sending fails (caught and displayed to user)
    """
    use_liacs = st.secrets.get("USE_LIACS_EMAIL", False)
    from_addr = "bs-internships@liacs.leidenuniv.nl"
    to_addr = f"{student_number}@vuw.leidenuniv.nl"
    subject = "Interview Verification Code"
    body = (
        "This is an automated email, please do not reply.\n\n"
        f"Your verification code is: {code}\n\n"
        "Enter this code in the interview window to continue."
    )

    if use_liacs:
        python_code = f"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

msg = MIMEMultipart()
msg['Subject'] = {repr(subject)}
msg['From'] = {repr(from_addr)}
msg['To'] = {repr(to_addr)}

body = {repr(body)}
msg.attach(MIMEText(body, 'plain'))

with smtplib.SMTP('smtp.leidenuniv.nl') as server:
    server.send_message(msg)

print('✅ Verification email sent.')
"""
        python_code = python_code.strip()
        encoded_code = base64.b64encode(python_code.encode()).decode()
        try:
            ssh_host = "ssh.liacs.nl"
            ssh_username = st.secrets["LIACS_SSH_USERNAME"]
            key_str = st.secrets["LIACS_SSH_KEY"]
            key_str = format_private_key(key_str)
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
            ssh.exec_command(remote_cmd)
            ssh.close()
            os.remove(tmp_key_path)
        except Exception as e:
            st.error("❌ Failed to send verification email via LIACS SMTP.")
            st.exception(e)
    else:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = "businessinternship.liacs@gmail.com"
        sender_password = st.secrets["EMAIL_PASSWORD"]
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_addr, msg.as_string())
            server.quit()
            st.success(f"📬 Verification email sent to {to_addr}")
        except Exception as e:
            st.error("Error sending verification email via Gmail SMTP.")
            st.exception(e)
