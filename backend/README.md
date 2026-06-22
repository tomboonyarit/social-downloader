# Social Media Downloader — Backend REST API

FastAPI backend สำหรับดาวน์โหลดรูป/วิดีโอจาก Social Network โดยใช้ **yt-dlp Python API** (ไม่ใช้ subprocess)

## 📋 Requirements

- Python 3.10+
- ffmpeg (สำหรับ merge video+audio streams)
- curl_cffi (ติดตั้งอัตโนมัติพร้อม yt-dlp — ใช้ TLS impersonation)

## 🚀 Quick Start

```bash
# 1. ติดตั้ง dependencies
pip install -r requirements.txt

# 2. ตั้งค่า API Key (optional - ถ้าไม่ตั้งจะไม่ต้องใช้ auth)
export API_KEY="your-secret-key-here"

# 3. รัน server
uvicorn main:app --host 0.0.0.0 --port 8000
```

เปิด浏览器ไปที่ [http://localhost:8000/docs](http://localhost:8000/docs) สำหรับ Swagger UI

## 🔐 Authentication

API ใช้ **API Key authentication** ผ่าน header `X-API-Key`

```bash
curl -H "X-API-Key: your-secret-key-here" http://localhost:8000/api/platforms
```

ถ้าไม่ได้ตั้งค่า `API_KEY` environment จะไม่มีการตรวจสอบ (open access)

## 📡 Endpoints

### `POST /api/download`
ดาวน์โหลด media จาก URL

**Request:**
```json
{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Response:** Binary file (video/mp4, image/jpeg, audio/mpeg, etc.)
**Headers เพิ่มเติม:** `X-Download-Platform`, `X-Download-Size`

### `POST /api/info`
ดูข้อมูล media ก่อนดาวน์โหลด (title, duration, available formats, ฯลฯ)

**Request:** เหมือน `/api/download`

**Response:**
```json
{
    "title": "Rick Astley - Never Gonna Give You Up",
    "extractor": "youtube",
    "duration": 212,
    "thumbnail": "https://i.ytimg.com/vi/...",
    "platform": "youtube",
    "formats": [
        {
            "format_id": "137+140",
            "ext": "mp4",
            "resolution": "1920x1080",
            "filesize": 52428800,
            "vcodec": "avc1.640028",
            "acodec": "mp4a.40.2"
        }
    ]
}
```

### `GET /api/platforms`
รายชื่อ platform ที่รองรับ

**Response:**
```json
[
    {
        "id": "youtube",
        "name": "YouTube",
        "url_pattern": "youtube.com/*, youtu.be/*",
        "max_quality": "8K",
        "status": "✅ Excellent",
        "notes": "Best-in-class support. DASH formats up to 8K."
    }
]
```

### `GET /`
Health check

## 🛠️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `sk-soc...-dev` | API key สำหรับ X-API-Key auth |
| `DOWNLOAD_DIR` | `./downloads/` | Directory สำหรับไฟล์ชั่วคราว |
| `MAX_CONCURRENT` | `3` | จำนวน download พร้อมกันสูงสุด |
| `PORT` | `8000` | Port ที่รัน server |
| `HOST` | `0.0.0.0` | Host interface |
| `RELOAD` | `false` | Auto-reload เมื่อแก้ไขโค้ด (dev mode) |
| `DEBUG` | (none) | แสดง stack trace ใน error response |

## 📦 Architecture

```
POST /api/download ──→ asyncio.Queue ──→ ThreadPoolExecutor ──→ yt-dlp (YoutubeDL)
                        (rate limit)       (yt-dlp is blocking)   (Python API)
```

- ใช้ `asyncio.Semaphore` สำหรับ rate limiting
- ใช้ `loop.run_in_executor()` รัน yt-dlp แบบ blocking ใน thread pool
- ดาวน์โหลดไฟล์ไปยัง temp dir → stream กลับ → cleanup อัตโนมัติ

## 🎯 Supported Platforms

| Platform | Status | Max Quality | Notes |
|----------|--------|-------------|-------|
| YouTube | ✅ Excellent | 8K | DASH formats, playlists |
| TikTok | ✅ Good | 1080p | play_addr = no watermark |
| Instagram | ⚠️ Partial | 1080p | Single post/reel only; user extractor broken |
| Twitter / X | ✅ Good | 1080p | 3 backend modes; syndication fallback |
| Facebook | ⚠️ Fragile | 1080p | Login support removed Dec 2025 |

## ⚙️ yt-dlp Configuration

อ้างอิงจาก [Social Media APIs Research Report](../../kanban/workspaces/t_f681803a/Social-Media-APIs-Research-Report.md):

- Format selection: `bv*+ba/b` (best video + best audio, merged with ffmpeg)
- TLS impersonation: `chrome-99`
- Sleep interval: 5s (15s max) — polite crawling
- Retry: linear=1:2:10, max 10 retries
- Geo-bypass: `xff default`

## ⚠️ Legal Disclaimer

**ข้อจำกัดความรับผิดชอบ:** เครื่องมือนี้ใช้ yt-dlp ซึ่งทำงานโดย reverse-engineer internal APIs ของ social media platforms การใช้เครื่องมือนี้

1. **อาจผิด ToS** ของ platform นั้น ๆ (YouTube Section 4.C, TikTok Section L62, etc.)
2. **สำหรับใช้ส่วนตัวเท่านั้น** — ไม่แนะนำให้ใช้ในเชิงพาณิชย์
3. **เนื้อหาที่มีลิขสิทธิ์** — ผู้ใช้ต้องรับผิดชอบเองในการดาวน์โหลดเนื้อหาที่มี版权

ดูรายละเอียดเพิ่มเติมใน research report

## 🔧 Production Deployment

```bash
# ใช้ Gunicorn + Uvicorn workers
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app

# หรือ Docker
docker run -p 8000:8000 -e API_KEY=xxx ...
```

---

พัฒนาโดย Nous Research | สำหรับคุณพ่อเลี้ยงต้อม (tom) 💙
