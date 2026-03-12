from types import SimpleNamespace

import secrets_utils


def test_get_secret_reads_local_file_when_streamlit_secrets_are_unavailable(
    monkeypatch, tmp_path
):
    secrets_file = tmp_path / "secrets.toml"
    secrets_file.write_text('LIACS_SSH_USERNAME = "local-user"\n', encoding="utf-8")

    monkeypatch.setenv("STREAMLIT_SECRETS_PATH", str(secrets_file))

    class BrokenSecrets:
        def __contains__(self, key):
            raise RuntimeError("outside streamlit")

    monkeypatch.setattr(secrets_utils, "st", SimpleNamespace(secrets=BrokenSecrets()))
    secrets_utils.load_local_secrets.cache_clear()

    assert secrets_utils.get_secret("LIACS_SSH_USERNAME") == "local-user"


def test_get_secret_prefers_streamlit_secrets(monkeypatch, tmp_path):
    secrets_file = tmp_path / "secrets.toml"
    secrets_file.write_text('LIACS_SSH_USERNAME = "local-user"\n', encoding="utf-8")

    monkeypatch.setenv("STREAMLIT_SECRETS_PATH", str(secrets_file))
    monkeypatch.setattr(
        secrets_utils,
        "st",
        SimpleNamespace(secrets={"LIACS_SSH_USERNAME": "streamlit-user"}),
    )
    secrets_utils.load_local_secrets.cache_clear()

    assert secrets_utils.get_secret("LIACS_SSH_USERNAME") == "streamlit-user"
