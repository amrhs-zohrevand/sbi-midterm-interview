import base64
import json
import os
import smtplib
import time
import urllib.error
import urllib.request
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from remote_utils import close_ssh_connection, get_ssh_connection, run_remote_python


def check_if_interview_completed(directory, username):
    """Check if an interview transcript/time file exists for a username."""
    if username == "testaccount":
        return False

    try:
        with open(os.path.join(directory, f"{username}.txt"), "r", encoding="utf-8") as _:
            return True
    except FileNotFoundError:
        return False


def _get_transcript_messages():
    """Return persisted conversation messages, excluding system instructions."""
    return [
        message
        for message in st.session_state.get("messages", [])
        if message.get("role") != "system"
    ]


def save_interview_data(
    student_number, company_name="", transcripts_directory=None, times_directory=None
):
    """Persist transcript and timing information to local files."""
    if transcripts_directory is None or times_directory is None:
        import config

        if transcripts_directory is None:
            transcripts_directory = config.TRANSCRIPTS_DIRECTORY
        if times_directory is None:
            times_directory = config.TIMES_DIRECTORY

    current_date = time.strftime("%y%m%d")
    session_id = st.session_state.session_id
    file_identifier = (student_number or "").strip() or session_id
    sanitized_company = (
        "".join(c for c in company_name if c.isalnum()) if company_name else ""
    )

    if sanitized_company:
        transcript_filename = (
            f"{current_date}_{file_identifier}_{sanitized_company}_transcript.txt"
        )
        time_filename = f"{current_date}_{file_identifier}_{sanitized_company}_time.txt"
    else:
        transcript_filename = f"{current_date}_{file_identifier}_transcript.txt"
        time_filename = f"{current_date}_{file_identifier}_time.txt"

    os.makedirs(transcripts_directory, exist_ok=True)
    os.makedirs(times_directory, exist_ok=True)
    transcript_file = os.path.join(transcripts_directory, transcript_filename)
    time_file = os.path.join(times_directory, time_filename)

    with open(transcript_file, "w", encoding="utf-8") as transcript_handle:
        transcript_handle.write(f"Session ID: {session_id}\n\n")
        for message in _get_transcript_messages():
            transcript_handle.write(f"{message['role']}: {message['content']}\n")

    with open(time_file, "w", encoding="utf-8") as time_handle:
        duration = (time.time() - st.session_state.start_time) / 60
        time_handle.write(
            f"Session ID: {session_id}\n"
            f"Start time (UTC): {time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )

    transcript_link = ""
    return transcript_link, transcript_file


def _extract_audio_from_response(response_obj):
    """Extract audio bytes and mime type from DeepInfra TTS responses."""
    if isinstance(response_obj, dict):
        for key in ("audio_url", "audio", "url", "output_url"):
            value = response_obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return _fetch_audio_url(value)

        for key in ("audio", "audio_data", "data", "output"):
            value = response_obj.get(key)
            if isinstance(value, dict):
                mime_type = value.get("mime_type") or value.get("content_type") or ""
                for data_key in (
                    "data",
                    "base64",
                    "audio_base64",
                    "wav_base64",
                    "mp3_base64",
                ):
                    data_val = value.get(data_key)
                    if isinstance(data_val, str):
                        try:
                            audio_bytes = base64.b64decode(data_val)
                        except Exception:
                            continue
                        return audio_bytes, mime_type or "audio/wav"

        for key in ("wav_base64", "audio_base64", "mp3_base64", "base64", "audio"):
            value = response_obj.get(key)
            if isinstance(value, str) and not value.startswith("http"):
                if value.startswith("data:audio/") and ";base64," in value:
                    header, b64_data = value.split(",", 1)
                    mime_type = header.replace("data:", "").split(";")[0]
                    try:
                        audio_bytes = base64.b64decode(b64_data)
                    except Exception:
                        continue
                    return audio_bytes, mime_type or "audio/wav"
                try:
                    audio_bytes = base64.b64decode(value)
                except Exception:
                    continue
                return audio_bytes, "audio/wav"

        for key in ("data", "result", "results", "output"):
            extracted = _extract_audio_from_response(response_obj.get(key))
            if extracted:
                return extracted
    elif isinstance(response_obj, list):
        for item in response_obj:
            extracted = _extract_audio_from_response(item)
            if extracted:
                return extracted

    return None


def _fetch_audio_url(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        audio_bytes = response.read()
        mime_type = response.headers.get("Content-Type", "")
    if not mime_type:
        mime_type = "audio/mpeg" if url.lower().endswith(".mp3") else "audio/wav"
    return audio_bytes, mime_type


def synthesize_speech_deepinfra(
    text,
    model="hexgrad/Kokoro-82M",
    api_key=None,
    voice=None,
    timeout=60,
):
    """
    Synthesize speech using DeepInfra TTS models.

    Returns (audio_bytes, mime_type).
    """
    if not api_key:
        raise ValueError("Missing DEEPINFRA_API_KEY for speech synthesis.")

    resolved_voice = voice or st.secrets.get("TTS_VOICE", "af_heart")
    voice_params = {
        "voice": resolved_voice,
        "preset_voice": resolved_voice,
        "preset_voices": [resolved_voice],
        "speaker": resolved_voice,
        "voice_id": resolved_voice,
    }
    payload = {
        "text": text,
        "input": text,
        "parameters": {
            **voice_params,
            "tts_response_format": "wav",
            "output_format": "wav",
        },
        **voice_params,
        "tts_response_format": "wav",
        "output_format": "wav",
    }
    data = json.dumps(payload).encode("utf-8")
    url = f"https://api.deepinfra.com/v1/inference/{model}"
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"DeepInfra TTS error: {exc.code} {detail}") from exc

    if content_type.startswith("audio/"):
        return body, content_type
    if content_type == "application/octet-stream":
        return body, "audio/wav"

    try:
        response_obj = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Unexpected DeepInfra TTS response format.") from exc

    extracted = _extract_audio_from_response(response_obj)
    if not extracted:
        raise RuntimeError(
            f"DeepInfra TTS response missing audio data. Response: {response_obj}"
        )
    return extracted


def _run_liacs_script(python_code: str, error_message: str) -> None:
    """Execute a small Python script on the LIACS host."""
    ssh = None
    tmp_key_path = None
    try:
        ssh, tmp_key_path = get_ssh_connection()
        output = run_remote_python(ssh, python_code.strip())
        if output:
            st.success(output)
    except Exception as exc:
        st.error(error_message)
        st.exception(exc)
    finally:
        close_ssh_connection(ssh, tmp_key_path)


def send_transcript_email(
    student_number,
    recipient_email,
    transcript_link,
    transcript_file,
    name_from_form=None,
):
    """
    Send the interview transcript via either Gmail or LIACS SMTP.

    *transcript_link* is retained for backward compatibility with the existing
    call sites, but the current implementation attaches the transcript file.
    """
    del transcript_link

    use_liacs = st.secrets.get("USE_LIACS_EMAIL", False)
    from_addr = "bs-internships@liacs.leidenuniv.nl"

    student_number = (student_number or "").strip()
    recipient_email = (recipient_email or "").strip()
    if student_number:
        to_addr = f"{student_number}@vuw.leidenuniv.nl"
        cc_addr = recipient_email
    else:
        to_addr = recipient_email
        cc_addr = ""

    bcc_addr = "a.h.zohrehvand@liacs.leidenuniv.nl"
    subject = "Your Interview Transcript from Leiden University"
    greeting_name = (
        name_from_form.strip()
        if name_from_form and name_from_form.strip()
        else "participant"
    )
    body = f"""\
This is an automated email, please do not reply.

Dear {greeting_name},

Thank you for participating in the interview. Your transcript has been saved and is attached to this email.

Best wishes,
Business Studies Internship Team
LIACS, Leiden University
"""

    file_name = os.path.basename(transcript_file) or "transcript.txt"

    if use_liacs:
        with open(transcript_file, "rb") as transcript_handle:
            attachment_data = base64.b64encode(transcript_handle.read()).decode()

        python_code = f"""\
import base64
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

msg = MIMEMultipart()
msg["Subject"] = {subject!r}
msg["From"] = {from_addr!r}
msg["To"] = {to_addr!r}
if {bool(cc_addr)!r}:
    msg["Cc"] = {cc_addr!r}
if {bool(bcc_addr)!r}:
    msg["Bcc"] = {bcc_addr!r}
msg.attach(MIMEText({body!r}, "plain"))

part = MIMEBase("text", "plain")
part.set_payload(base64.b64decode({attachment_data!r}))
encoders.encode_base64(part)
part.add_header("Content-Type", f'text/plain; name="{file_name}"')
part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')
msg.attach(part)

with smtplib.SMTP("smtp.leidenuniv.nl") as server:
    server.send_message(msg)

print("Email sent. Please wait with closing this window as we are still processing data.")
"""
        _run_liacs_script(python_code, "Failed to send email via LIACS SMTP.")
        return

    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "businessinternship.liacs@gmail.com"
    sender_password = st.secrets["EMAIL_PASSWORD"]

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_addr
    if cc_addr:
        msg["Cc"] = cc_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with open(transcript_file, "rb") as transcript_handle:
        content = transcript_handle.read()

    part = MIMEBase("text", "plain")
    part.set_payload(content)
    encoders.encode_base64(part)
    part.add_header("Content-Type", f'text/plain; name="{file_name}"')
    part.add_header("Content-Disposition", f'attachment; filename="{file_name}"')
    msg.attach(part)

    recipients = [addr for addr in [to_addr, cc_addr, bcc_addr] if addr]
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipients, msg.as_string())
        st.success(f"Email sent to {recipients}")
    except Exception as exc:
        st.error("Error sending email via Gmail SMTP.")
        st.exception(exc)


def send_verification_code(student_number, code):
    """Send a short verification code to the student's institutional email."""
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
        python_code = f"""\
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

msg = MIMEMultipart()
msg["Subject"] = {subject!r}
msg["From"] = {from_addr!r}
msg["To"] = {to_addr!r}
msg.attach(MIMEText({body!r}, "plain"))

with smtplib.SMTP("smtp.leidenuniv.nl") as server:
    server.send_message(msg)

print("Verification email sent.")
"""
        _run_liacs_script(python_code, "Failed to send verification email via LIACS SMTP.")
        return

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
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [to_addr], msg.as_string())
        st.success(f"Verification email sent to {to_addr}")
    except Exception as exc:
        st.error("Error sending verification email via Gmail SMTP.")
        st.exception(exc)
