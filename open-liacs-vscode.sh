#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${1:-liacs}"
REMOTE_PATH="${2:-/home/zohrehvanda/BS-Interviews}"

if ! command -v code >/dev/null 2>&1; then
  echo "VS Code CLI (code) is not installed or not on PATH." >&2
  exit 1
fi

exec code --folder-uri "vscode-remote://ssh-remote+${REMOTE_HOST}${REMOTE_PATH}"
