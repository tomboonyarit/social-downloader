#!/usr/bin/env bash
# Stop Social Downloader services
pkill -f "uvicorn main:app" 2>/dev/null && echo "Backend stopped" || echo "Backend not running"
pkill -f "python server.py" 2>/dev/null && echo "Gateway stopped" || echo "Gateway not running"
