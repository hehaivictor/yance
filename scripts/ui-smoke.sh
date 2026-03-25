#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
DEFAULT_BASE_URL="http://127.0.0.1:3100"
BASE_URL="${UI_SMOKE_BASE_URL:-$DEFAULT_BASE_URL}"
URL_NO_SCHEME="${BASE_URL#http://}"
URL_NO_SCHEME="${URL_NO_SCHEME#https://}"
URL_HOST_PORT="${URL_NO_SCHEME%%/*}"
HOST="${URL_HOST_PORT%:*}"
PORT="${URL_HOST_PORT##*:}"
LOG_FILE="$ROOT_DIR/.tmp-ui-smoke-frontend.log"
STARTED_FRONTEND=0

cleanup() {
  if [ "$STARTED_FRONTEND" -eq 1 ] && [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[ui-smoke] 前端依赖缺失，先执行 bootstrap"
  "$ROOT_DIR/scripts/bootstrap.sh"
fi

echo "[ui-smoke] 安装 Playwright Chromium"
(
  cd "$FRONTEND_DIR"
  npx playwright install chromium
)

if curl -fsS "$BASE_URL" >/dev/null 2>&1; then
  echo "[ui-smoke] 复用现有页面：$BASE_URL"
elif [ -z "${UI_SMOKE_BASE_URL:-}" ] && curl -fsS "http://127.0.0.1:3000" >/dev/null 2>&1; then
  BASE_URL="http://127.0.0.1:3000"
  echo "[ui-smoke] 发现现有开发服务，改为复用：$BASE_URL"
else
  echo "[ui-smoke] 构建并启动临时前端：$BASE_URL"
  (
    cd "$FRONTEND_DIR"
    NEXT_TELEMETRY_DISABLED=1 npm run build >/dev/null
  )
  (
    cd "$FRONTEND_DIR"
    NEXT_TELEMETRY_DISABLED=1 npm run start -- --hostname "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1
  ) &
  FRONTEND_PID=$!
  STARTED_FRONTEND=1

  for _ in $(seq 1 60); do
    if curl -fsS "$BASE_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! curl -fsS "$BASE_URL" >/dev/null 2>&1; then
    echo "[ui-smoke] 临时前端启动失败，日志如下："
    cat "$LOG_FILE"
    exit 1
  fi
fi

echo "[ui-smoke] 运行页面验收"
(
  cd "$FRONTEND_DIR"
  npm run smoke:ui -- --url="$BASE_URL"
)
