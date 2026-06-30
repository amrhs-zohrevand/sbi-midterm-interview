"""Materialize a Streamlit secrets.toml from environment variables.

App Platform (and most container hosts) inject configuration as environment
variables, but this app reads configuration from ``st.secrets`` and from a
``secrets.toml`` file (see ``secrets_utils.get_secret``) -- it does not read
``os.environ`` directly. This script bridges the gap: it runs once at container
start, writes the env-var values into the locations Streamlit and
``secrets_utils`` look for, and then the normal app starts unchanged.

Intended use in the App Platform run command:

    python prepare_do_secrets.py && streamlit run interview.py --server.port $PORT ...

Running locally is a no-op as long as none of the listed keys are exported,
so it is safe to keep in the run command in every environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Secret keys mirrored from code/.streamlit/secrets.toml.example.
# Only keys that are actually present in the environment are written.
STRING_KEYS = [
    "ENV",
    "API_PROVIDER",
    "MODEL",
    "API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPINFRA_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_SITE_URL",
    "OPENROUTER_APP_NAME",
    "OPENROUTER_DEFAULT_MODEL",
    "OPENROUTER_INDUSTRY_MODEL",
    "OPENROUTER_INDUSTRY_REASONING_EFFORT",
    "OPENROUTER_REASONING_MAX_TOKENS",
    "TTS_MODEL",
    "TTS_VOICE",
    "EMAIL_PASSWORD",
    "LIACS_SSH_USERNAME",
    "LIACS_SSH_KEY",
    "REMOTE_SSH_HOST",
    "REMOTE_SSH_USERNAME",
    "REMOTE_SSH_KEY",
    "REMOTE_DATABASE_DIRECTORY",
]

# Keys whose values must be rendered as TOML booleans, not strings. A quoted
# string like "false" would be truthy in Python, so these must be real booleans.
BOOLEAN_KEYS = ["USE_LIACS_EMAIL", "EMAIL_FALLBACK_TO_GMAIL"]

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _toml_lines() -> list[str]:
    lines: list[str] = []
    for key in STRING_KEYS:
        value = os.environ.get(key)
        if value:
            # json.dumps produces a valid TOML basic string, encoding any
            # newlines (e.g. in an SSH private key) as \n.
            lines.append(f"{key} = {json.dumps(value)}")
    for key in BOOLEAN_KEYS:
        value = os.environ.get(key)
        if value is not None and value != "":
            literal = "true" if value.strip().lower() in _TRUE_VALUES else "false"
            lines.append(f"{key} = {literal}")
    return lines


def _candidate_targets() -> list[Path]:
    # ~/.streamlit/secrets.toml is read both by Streamlit's native st.secrets
    # and by secrets_utils. The cwd copy is a belt-and-suspenders fallback.
    return [
        Path.home() / ".streamlit" / "secrets.toml",
        Path(".streamlit") / "secrets.toml",
    ]


def main() -> None:
    lines = _toml_lines()
    if not lines:
        print(
            "prepare_do_secrets: no known secret env vars found; "
            "leaving any existing secrets.toml untouched."
        )
        return

    content = "\n".join(lines) + "\n"
    written = []
    for target in _candidate_targets():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(str(target))
        except OSError as exc:  # pragma: no cover - best effort across hosts
            print(f"prepare_do_secrets: could not write {target}: {exc}")

    # Never log the values themselves, only which keys were materialized.
    keys = ", ".join(line.split(" = ", 1)[0] for line in lines)
    print(
        f"prepare_do_secrets: wrote {len(lines)} secret(s) "
        f"[{keys}] to {', '.join(written) or '(no writable location)'}"
    )


if __name__ == "__main__":
    main()
