#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -d "$BACKEND_DIR/.venv" ] || [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[dev] missing dependencies, running bootstrap first"
  "$ROOT_DIR/scripts/bootstrap.sh"
fi

cleanup() {
  local exit_code=$?
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup INT TERM EXIT

echo "[dev] backend -> http://127.0.0.1:8000"
(
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "[dev] frontend -> http://127.0.0.1:3000"
(
  cd "$FRONTEND_DIR"
  exec npm run dev -- --hostname 127.0.0.1 --port 3000
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
