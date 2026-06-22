#!/usr/bin/env bash
# ================================================================
# Watchdog — ตรวจสอบ service และ restart อัตโนมัติ
# รันโดย Hermes cron job ทุก 5 นาที
# ================================================================
set -e

BACKEND_DIR="/opt/data/projects/social-downloader/backend"
FRONTEND_DIR="/opt/data/projects/social-downloader/frontend"
VENV="${BACKEND_DIR}/.venv"
LOG_DIR="/opt/data/projects/social-downloader/logs"
TS=$(date +%Y%m%d-%H%M%S)

mkdir -p "${LOG_DIR}"

# ตรวจสอบ Backend (port 8000)
if ! curl -sf http://localhost:8000/ >/dev/null 2>&1; then
    echo "[${TS}] 🔴 Backend ไม่ทำงาน — กำลัง restart..."
    cd "${BACKEND_DIR}"
    source "${VENV}/bin/activate"
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
        > "${LOG_DIR}/backend-${TS}.log" 2>&1 &
    echo "[${TS}] ✅ Backend started (PID $!)"
    RESTARTED=1
else
    echo "[${TS}] 🟢 Backend ทำงานปกติ"
fi

# ตรวจสอบ Gateway (port 8443)
if ! curl -sfk https://localhost:8443/ >/dev/null 2>&1; then
    echo "[${TS}] 🔴 Gateway ไม่ทำงาน — กำลัง restart..."
    cd "${FRONTEND_DIR}"
    source "${VENV}/bin/activate"
    nohup python server.py \
        > "${LOG_DIR}/gateway-${TS}.log" 2>&1 &
    echo "[${TS}] ✅ Gateway started (PID $!)"
    RESTARTED=1
else
    echo "[${TS}] 🟢 Gateway ทำงานปกติ"
fi

if [ -n "$RESTARTED" ]; then
    echo "[${TS}] 🔄 มีการ restart service"
else
    echo "[${TS}] ✅ ทุกอย่างปกติ"
fi
