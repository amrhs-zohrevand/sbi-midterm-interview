from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
import tomllib

import streamlit as st


def _candidate_secret_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[1]
    candidates = []

    env_path = os.environ.get("STREAMLIT_SECRETS_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        [
            repo_root / "code" / ".streamlit" / "secrets.toml",
            repo_root / ".streamlit" / "secrets.toml",
            Path.home() / ".streamlit" / "secrets.toml",
        ]
    )
    return candidates


@lru_cache(maxsize=1)
def load_local_secrets() -> dict:
    for path in _candidate_secret_paths():
        if not path.is_file():
            continue
        with path.open("rb") as secrets_file:
            return tomllib.load(secrets_file)
    return {}


def get_secret(key: str, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return load_local_secrets().get(key, default)
