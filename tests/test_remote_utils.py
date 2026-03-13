import ast
import base64
import json
from pathlib import Path

import remote_utils


def _extract_payload(python_code: str):
    for line in python_code.splitlines():
        if "base64.b64decode(" in line:
            encoded_literal = line.split("base64.b64decode(", 1)[1].split(
                ").decode()", 1
            )[0]
            encoded_payload = ast.literal_eval(encoded_literal)
            return json.loads(base64.b64decode(encoded_payload).decode())
    raise AssertionError("Could not find encoded SQL payload in remote script.")


def test_format_private_key_replaces_escaped_newlines():
    raw_key = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\\nABCDEF123456\\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    formatted = remote_utils.format_private_key(raw_key)
    assert "\\n" not in formatted
    assert formatted.startswith("-----BEGIN OPENSSH PRIVATE KEY-----\n")


def test_close_ssh_connection_closes_client_and_removes_temp_file(tmp_path):
    removed_file = tmp_path / "temp-key"
    removed_file.write_text("key")

    class FakeSSH:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    ssh = FakeSSH()
    remote_utils.close_ssh_connection(ssh, str(removed_file))

    assert ssh.closed is True
    assert not removed_file.exists()


def test_run_remote_sql_encodes_query_params_and_decodes_fetch_result(monkeypatch):
    captured = {}

    def fake_run_remote_python(ssh, python_code):
        captured["payload"] = _extract_payload(python_code)
        return '["saved summary"]'

    monkeypatch.setattr(remote_utils, "run_remote_python", fake_run_remote_python)

    result = remote_utils.run_remote_sql(
        object(),
        "/tmp/interviews.db",
        "SELECT summary FROM interviews WHERE student_id = ?",
        ["s123"],
        fetch="one",
    )

    assert captured["payload"] == {
        "db_path": "/tmp/interviews.db",
        "sql_query": "SELECT summary FROM interviews WHERE student_id = ?",
        "params": ["s123"],
        "fetch": "one",
    }
    assert result == ["saved summary"]


def test_run_remote_sql_returns_none_for_non_fetch_queries(monkeypatch):
    called = {}

    def fake_run_remote_python(ssh, python_code):
        called["payload"] = _extract_payload(python_code)
        return ""

    monkeypatch.setattr(remote_utils, "run_remote_python", fake_run_remote_python)

    result = remote_utils.run_remote_sql(
        object(),
        "/tmp/interviews.db",
        "UPDATE interviews SET summary = ? WHERE interview_id = ?",
        ["summary", "id-1"],
    )

    assert result is None
    assert called["payload"]["params"] == ["summary", "id-1"]


def test_run_remote_sql_batch_encodes_operations_and_decodes_results(monkeypatch):
    captured = {}

    def fake_run_remote_python(ssh, python_code):
        captured["payload"] = _extract_payload(python_code)
        return '[["summary text"], [[0, "survey_helpfulness", "TEXT", 0, null, 0]]]'

    monkeypatch.setattr(remote_utils, "run_remote_python", fake_run_remote_python)

    result = remote_utils.run_remote_sql_batch(
        object(),
        "/tmp/interviews.db",
        [
            {
                "type": "execute",
                "sql_query": "SELECT summary FROM interviews WHERE interview_id = ?",
                "params": ["id-1"],
                "fetch": "one",
            },
            {
                "type": "ensure_columns",
                "table": "interviews",
                "columns": {"survey_helpfulness": "TEXT"},
            },
            {
                "type": "execute",
                "sql_query": "PRAGMA table_info(interviews)",
                "fetch": "all",
            },
        ],
    )

    assert captured["payload"] == {
        "db_path": "/tmp/interviews.db",
        "operations": [
            {
                "type": "execute",
                "sql_query": "SELECT summary FROM interviews WHERE interview_id = ?",
                "params": ["id-1"],
                "fetch": "one",
            },
            {
                "type": "ensure_columns",
                "table": "interviews",
                "columns": {"survey_helpfulness": "TEXT"},
            },
            {
                "type": "execute",
                "sql_query": "PRAGMA table_info(interviews)",
                "fetch": "all",
            },
        ],
    }
    assert result == [["summary text"], [[0, "survey_helpfulness", "TEXT", 0, None, 0]]]
