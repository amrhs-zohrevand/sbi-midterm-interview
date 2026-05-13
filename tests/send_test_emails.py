#!/usr/bin/env python
"""Integration test: actually sends emails via Gmail SMTP to verify delivery.

Run from the project root:
    python tests/send_test_emails.py

Two emails should arrive at j.s.deweert@gmail.com:
  1. Student interview flow  — sent as CC (student_number present)
  2. Industry/org survey flow — sent as primary TO (no student_number)

Uses Gmail SMTP regardless of USE_LIACS_EMAIL so LIACS SSH is not required.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli for Python < 3.11
    except ImportError:
        print("ERROR: tomllib not found. Install tomli: pip install tomli", file=sys.stderr)
        sys.exit(1)

import utils

SECRETS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "code", ".streamlit", "secrets.toml"
)
TEST_EMAIL = "j.s.deweert@gmail.com"


def _load_secrets():
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)


class _FakeSecrets:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]


class _FakeSt:
    def __init__(self, secrets_dict):
        self.secrets = _FakeSecrets(secrets_dict)

    def success(self, msg):
        print(f"  [ok] {msg}")

    def error(self, msg):
        print(f"  [error] {msg}", file=sys.stderr)

    def exception(self, exc):
        import traceback
        traceback.print_exc()


def _make_transcript(tmp_path):
    path = os.path.join(tmp_path, "test_transcript.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "Session ID: test-integration-001\n\n"
            "assistant: Hello, let's begin the interview.\n"
            "user: Sure, happy to participate.\n"
            "assistant: Great. This is a test transcript.\n"
        )
    return path


def main():
    raw_secrets = _load_secrets()
    # Force Gmail path so LIACS SSH is not required for this manual test
    secrets_override = dict(raw_secrets, USE_LIACS_EMAIL=False)
    utils.st = _FakeSt(secrets_override)

    with tempfile.TemporaryDirectory() as tmp:
        transcript = _make_transcript(tmp)

        print("=" * 60)
        print("Scenario 1: Student interview (CC -> gmail)")
        print(f"  student_number : s3075400 (test)")
        print(f"  CC email       : {TEST_EMAIL}")
        print("=" * 60)
        utils.send_transcript_email(
            student_number="s3075400",
            recipient_email=TEST_EMAIL,
            transcript_link="",
            transcript_file=transcript,
            name_from_form="Justin de Weert (test student)",
        )

        print()
        print("=" * 60)
        print("Scenario 2: Industry/org survey (TO -> gmail directly)")
        print(f"  student_number : (none)")
        print(f"  TO email       : {TEST_EMAIL}")
        print("=" * 60)
        utils.send_transcript_email(
            student_number="",
            recipient_email=TEST_EMAIL,
            transcript_link="",
            transcript_file=transcript,
            name_from_form="Justin de Weert (test industry)",
        )

    print()
    print(f"Done. Check {TEST_EMAIL} for both test emails.")


if __name__ == "__main__":
    main()
