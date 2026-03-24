#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "[bootstrap] root: $ROOT_DIR"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "[bootstrap] create python venv"
  python3 -m venv "$BACKEND_DIR/.venv"
fi

echo "[bootstrap] install backend dependencies"
(
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
)

echo "[bootstrap] install frontend dependencies"
(
  cd "$FRONTEND_DIR"
  npm install
)

echo "[bootstrap] done"
