#!/usr/bin/env bash
set -euo pipefail

backend_pid=""
cleanup() {
  if [[ -n "${backend_pid}" ]]; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --reload --port 8009 &
backend_pid=$!

cd frontend
VITE_API_MODE=real npm run dev -- --host 0.0.0.0
