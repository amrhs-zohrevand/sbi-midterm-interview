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
        self.exceptions = []

    def success(self, message):
        self.success_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)

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

    utils.send_transcript_email(
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
    assert fake_st.success_messages


def test_send_transcript_email_liacs_path_delegates_to_remote_runner(
    monkeypatch, tmp_path
):
    fake_st = FakeStreamlit(secrets={"USE_LIACS_EMAIL": True})
    monkeypatch.setattr(utils, "st", fake_st)

    calls = []
    monkeypatch.setattr(
        utils,
        "_run_liacs_script",
        lambda python_code, error_message: calls.append((python_code, error_message)),
    )

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("assistant: hello", encoding="utf-8")

    utils.send_transcript_email(
        student_number="123456",
        recipient_email="person@example.com",
        transcript_link="",
        transcript_file=str(transcript_file),
        name_from_form="Miros",
    )

    assert len(calls) == 1
    assert "smtp.leidenuniv.nl" in calls[0][0]
    assert calls[0][1] == "Failed to send email via LIACS SMTP."


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
