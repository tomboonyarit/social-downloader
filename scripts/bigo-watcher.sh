#!/usr/bin/env bash
# ================================================================
# Bigo TV Live Watcher
# ================================================================
# Checks if a specific Bigo TV channel is currently live.
# When detected live, sends notification via cron delivery.
# Uses state file to avoid duplicate notifications.
# When channel goes offline, resets state for next live event.
# ================================================================
set -euo pipefail

# ---- Configuration ----
CHANNEL_URL="https://www.bigo.tv/th/sid/2516954279_4026354474_1782142971?c=6&p=2&t=0&b=13813911&h=n.nuview"
STATES_DIR="/opt/data/projects/social-downloader/scripts/.states"
mkdir -p "$STATES_DIR"
STATE_FILE="$STATES_DIR/bigo_live_notified_2516954279.state"

CHANNEL_ID="2516954279"
YT_DLP="/opt/data/projects/social-downloader/backend/.venv/bin/yt-dlp"

# ---- Check live status ----
# yt-dlp exits 0 on success (live or VOD), 1 on "not currently live"
# We capture title only on success
output=$("$YT_DLP" --skip-download --print "%(title)s" "$CHANNEL_URL" 2>/dev/null) || true

if [ -n "$output" ]; then
    # Channel is live!
    if [ ! -f "$STATE_FILE" ]; then
        # First detection — notify
        touch "$STATE_FILE"
        echo "🔴 Bigo TV กำลังสตรีมสดแล้วค่า!

┌─ ช่อง: Bigo ID $CHANNEL_ID
├─ เรื่อง: $output
├─ เวลา: $(TZ=Asia/Bangkok date '+%d/%m/%Y %H:%M')
└─ ดูได้ที่: $CHANNEL_URL

กดลิงก์เลยค่า! 🔥"
    fi
else
    # Not live — reset state so we can notify next time
    rm -f "$STATE_FILE"
fi
