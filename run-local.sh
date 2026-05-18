#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Expected virtual environment at $ROOT_DIR/.venv" >&2
  echo "Create it first with:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r code/requirements.txt" >&2
  exit 1
fi

cd "$ROOT_DIR/code"
exec "$PYTHON_BIN" -m streamlit run interview.py "$@"
