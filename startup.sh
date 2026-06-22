# ~/.bashrc — user shell config
# Auto-start Social Downloader services on shell login

__social_downloader_start() {
    PROJECT="/opt/data/projects/social-downloader"
    VENV="${PROJECT}/backend/.venv"
    if [ -f "${VENV}/bin/activate" ]; then
        . "${VENV}/bin/activate"
        # Backend (port 8000)
        if ! curl -sf http://localhost:8000/ >/dev/null 2>&1; then
            cd "${PROJECT}/backend"
            nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
                > "${PROJECT}/logs/backend.log" 2>&1 &
            echo "[bashrc] Social Downloader backend started (port 8000)"
        fi
        # Gateway (port 8080) — serves frontend + proxies /api/ to backend
        if ! curl -sf http://localhost:8080/ >/dev/null 2>&1; then
            cd "${PROJECT}/frontend"
            nohup python server.py \
                > "${PROJECT}/logs/gateway.log" 2>&1 &
            echo "[bashrc] Social Downloader gateway started (port 8080)"
        fi
    fi
}
__social_downloader_start
