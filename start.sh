#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f frontend/dist/index.html ]]; then
  printf '%s\n' 'Brak kompilacji aplikacji. Uruchom: cd frontend && npm ci && npm run build' >&2
  exit 1
fi
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m uvicorn backend.app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
fi
exec python -m uvicorn backend.app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
