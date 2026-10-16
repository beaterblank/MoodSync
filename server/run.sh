#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  python -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
set -a
[[ -f .env ]] && source .env
set +a
exec .venv/bin/uvicorn moodsync.app:app --host "${MOODSYNC_HOST:-0.0.0.0}" --port "${MOODSYNC_PORT:-8088}"
