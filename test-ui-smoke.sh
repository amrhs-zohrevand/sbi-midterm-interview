#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to run the browser smoke test." >&2
  exit 1
fi

cd "$ROOT_DIR"
if [[ ! -d "$ROOT_DIR/node_modules/@playwright/test" ]]; then
  npm install
fi

npx playwright install chromium >/dev/null
npx playwright test -c tests/ui/playwright.config.mjs
