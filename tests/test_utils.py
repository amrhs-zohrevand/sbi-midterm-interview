import base64
import json
from pathlib import Path

import utils


class FakeSessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FakeStreamlit:
    def __init__(self, session_state=None, secrets=None):
        self.session_state = session_state or FakeSessionState()
        self.secrets = secrets or {}
        self.success_messages = []
        self.error_messages = []
        self.info_messages = []
        self.warning_messages = []
        self.exceptions = []

    def success(self, message):
        self.success_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)

    def info(self, message):
        self.info_messages.append(message)

    def warning(self, message):
        self.warning_messages.append(message)

    def exception(self, exc):
        self.exceptions.append(exc)


class FakeSMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        self.started_tls = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def sendmail(self, sender, recipients, message):
        self.sent = (sender, recipients, message)


def test_save_interview_data_uses_session_id_when_student_number_missing(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(
        session_state=FakeSessionState(
            session_id="session-123",
            start_time=0,
            messages=[
                {"role": "system", "content": "secret"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Hi"},
            ],
        )
    )
    monkeypatch.setattr(utils, "st", fake_st)

    transcripts_directory = tmp_path / "transcripts"
    times_directory = tmp_path / "times"
    _, transcript_file = utils.save_interview_data(
        student_number="",
        company_name="Acme!",
        transcripts_directory=str(transcripts_directory),
        times_directory=str(times_directory),
    )

    transcript_path = Path(transcript_file)
    assert transcript_path.exists()
    assert "session-123" in transcript_path.name
    transcript_text = transcript_path.read_text()
    assert "system: secret" not in transcript_text
    assert "assistant: Hello" in transcript_text
    assert "user: Hi" in transcript_text


def test_send_transcript_email_gmail_path_includes_bcc_and_avoids_empty_cc(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(secrets={"USE_LIACS_EMAIL": False, "EMAIL_PASSWORD": "pw"})
    monkeypatch.setattr(utils, "st", fake_st)

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="",
        recipient_email="person@example.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    smtp_client = sent_clients[0]
    assert smtp_client.host == "smtp.gmail.com"
    assert smtp_client.logged_in == ("businessinternship.liacs@gmail.com", "pw")
    assert smtp_client.sent[1] == [
        "person@example.com",
        "a.h.zohrehvand@liacs.leidenuniv.nl",
    ]
    assert result.sent is True
    assert result.provider == "gmail"
    assert fake_st.success_messages


def test_send_transcript_email_dedupes_audit_bcc(monkeypatch, tmp_path):
    fake_st = FakeStreamlit(secrets={"USE_LIACS_EMAIL": False, "EMAIL_PASSWORD": "pw"})
    monkeypatch.setattr(utils, "st", fake_st)

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="",
        recipient_email="a.h.zohrehvand@liacs.leidenuniv.nl",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert sent_clients[0].sent[1] == ["a.h.zohrehvand@liacs.leidenuniv.nl"]
    assert result.recipients == ["a.h.zohrehvand@liacs.leidenuniv.nl"]


def test_send_transcript_email_liacs_path_delegates_to_remote_runner(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(secrets={"USE_LIACS_EMAIL": True})
    monkeypatch.setattr(utils, "st", fake_st)

    calls = []

    def fake_run_liacs_script(python_code, error_message, show_error=True):
        calls.append((python_code, error_message, show_error))

    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        fake_run_liacs_script,
    )

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="123456",
        recipient_email="person@example.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert len(calls) == 1
    assert "smtp.leidenuniv.nl" in calls[0][0]
    assert calls[0][1] == "Failed to send email via LIACS SMTP."
    assert calls[0][2] is False
    assert result.sent is True
    assert result.provider == "liacs"


def test_send_transcript_email_uses_gmail_for_gmail_recipient_when_liacs_enabled(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(
        secrets={"USE_LIACS_EMAIL": True, "EMAIL_PASSWORD": "pw"}
    )
    monkeypatch.setattr(utils, "st", fake_st)
    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LIACS should be skipped for Gmail recipients")
        ),
    )

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="",
        recipient_email="person@gmail.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert sent_clients[0].host == "smtp.gmail.com"
    assert sent_clients[0].sent[1] == [
        "person@gmail.com",
        "a.h.zohrehvand@liacs.leidenuniv.nl",
    ]
    assert result.sent is True
    assert result.provider == "gmail_recipient"
    assert fake_st.info_messages == [
        "Sending Gmail recipient through Gmail backup delivery."
    ]


def test_send_transcript_email_falls_back_to_gmail_when_liacs_fails(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(
        secrets={
            "USE_LIACS_EMAIL": True,
            "EMAIL_PASSWORD": "pw",
        }
    )
    monkeypatch.setattr(utils, "st", fake_st)

    show_error_values = []

    def fake_run_liacs_script(python_code, error_message, show_error=True):
        show_error_values.append(show_error)
        return False, "ssh timed out"

    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        fake_run_liacs_script,
    )

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="",
        recipient_email="person@example.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert sent_clients[0].host == "smtp.gmail.com"
    assert result.sent is True
    assert result.provider == "gmail_fallback"
    assert "LIACS SMTP failed: ssh timed out" in result.error
    assert show_error_values == [False]
    assert fake_st.warning_messages == [
        "LIACS email failed. Trying Gmail backup delivery."
    ]


def test_send_transcript_email_can_disable_gmail_fallback(monkeypatch, tmp_path):
    fake_st = FakeStreamlit(
        secrets={
            "USE_LIACS_EMAIL": True,
            "EMAIL_PASSWORD": "pw",
            "EMAIL_FALLBACK_TO_GMAIL": False,
        }
    )
    monkeypatch.setattr(utils, "st", fake_st)

    show_error_values = []

    def fake_run_liacs_script(python_code, error_message, show_error=True):
        show_error_values.append(show_error)
        return False, "ssh timed out"

    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        fake_run_liacs_script,
    )
    monkeypatch.setattr(
        utils.smtplib,
        "SMTP",
        lambda host, port: (_ for _ in ()).throw(AssertionError("no Gmail fallback")),
    )

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    result = utils.send_transcript_email(
        student_number="",
        recipient_email="person@example.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert result.sent is False
    assert result.provider == "liacs"
    assert result.error == "ssh timed out"
    assert show_error_values == [True]


def test_send_verification_code_gmail_path_sends_to_expected_address(
    monkeypatch,
):
    fake_st = FakeStreamlit(secrets={"USE_LIACS_EMAIL": False, "EMAIL_PASSWORD": "pw"})
    monkeypatch.setattr(utils, "st", fake_st)

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    utils.send_verification_code("s12345", "654321")

    smtp_client = sent_clients[0]
    assert smtp_client.sent[1] == ["s12345@vuw.leidenuniv.nl"]
    assert fake_st.success_messages == [
        "Verification email sent to s12345@vuw.leidenuniv.nl"
    ]


def test_send_verification_code_falls_back_to_gmail_when_liacs_fails(monkeypatch):
    fake_st = FakeStreamlit(
        secrets={
            "USE_LIACS_EMAIL": True,
            "EMAIL_PASSWORD": "pw",
        }
    )
    monkeypatch.setattr(utils, "st", fake_st)

    show_error_values = []

    def fake_run_liacs_script(python_code, error_message, show_error=True):
        show_error_values.append(show_error)
        return False, "ssh timed out"

    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        fake_run_liacs_script,
    )

    sent_clients = []

    def fake_smtp_factory(host, port):
        client = FakeSMTP(host, port)
        sent_clients.append(client)
        return client

    monkeypatch.setattr(utils.smtplib, "SMTP", fake_smtp_factory)

    result = utils.send_verification_code("s12345", "654321")

    assert sent_clients[0].host == "smtp.gmail.com"
    assert sent_clients[0].sent[1] == ["s12345@vuw.leidenuniv.nl"]
    assert result.sent is True
    assert result.provider == "gmail_fallback"
    assert "LIACS SMTP failed: ssh timed out" in result.error
    assert show_error_values == [False]
    assert fake_st.warning_messages == [
        "LIACS verification email failed. Trying Gmail backup delivery."
    ]


def test_extract_audio_from_response_reads_nested_base64_audio():
    encoded_audio = base64.b64encode(b"wav-bytes").decode("ascii")
    response = {
        "result": {
            "audio": {
                "base64": encoded_audio,
                "mime_type": "audio/wav",
            }
        }
    }

    assert utils._extract_audio_from_response(response) == (b"wav-bytes", "audio/wav")


def test_synthesize_speech_deepinfra_decodes_json_audio_payload(monkeypatch):
    payload = {
        "audio": {
            "base64": base64.b64encode(b"audio-data").decode("ascii"),
            "mime_type": "audio/wav",
        }
    }

    class FakeResponse:
        def __init__(self):
            self.headers = {"Content-Type": "application/json"}

        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(utils.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    audio_bytes, mime_type = utils.synthesize_speech_deepinfra(
        "Hello world",
        api_key="secret",
        voice="af_heart",
    )

    assert audio_bytes == b"audio-data"
    assert mime_type == "audio/wav"
