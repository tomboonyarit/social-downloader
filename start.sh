#!/usr/bin/env bash
# ================================================================
# Social Downloader — Startup Script
# Starts the backend (port 8000) and gateway (port 8080).
# Designed to be called from cron @reboot or run manually.
# ================================================================
set -e

PROJECT_DIR="/opt/data/projects/social-downloader"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
VENV="${BACKEND_DIR}/.venv"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "${LOG_DIR}"

# Timestamp for log files
TS=$(date +%Y%m%d-%H%M%S)

echo "[$(date)] Starting Social Downloader services..."

# 1. Start/ensure backend on port 8000
if ! curl -sf http://localhost:8000/ >/dev/null 2>&1; then
    echo "[$(date)] Starting backend on port 8000..."
    cd "${BACKEND_DIR}"
    source "${VENV}/bin/activate"
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
        > "${LOG_DIR}/backend-${TS}.log" 2>&1 &
    echo "[$(date)] Backend started (PID $!)"
    sleep 2
else
    echo "[$(date)] Backend already running on port 8000"
fi

# 2. Start/ensure HTTPS gateway on port 8443
if ! curl -sfk https://localhost:8443/ >/dev/null 2>&1; then
    echo "[$(date)] Starting HTTPS gateway on port 8443..."
    cd "${FRONTEND_DIR}"
    source "${VENV}/bin/activate"
    nohup python server.py \
        > "${LOG_DIR}/gateway-${TS}.log" 2>&1 &
    echo "[$(date)] Gateway started (PID $!)"
else
    echo "[$(date)] Gateway already running on port 8443"
fi

echo "[$(date)] Social Downloader services are running."
echo "[$(date)]   Backend:  http://localhost:8000"
echo "[$(date)]   Gateway:  https://0.0.0.0:8443 (use this for UI)"
