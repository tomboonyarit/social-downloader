# Social Media Downloader — Frontend Web UI

Frontend แบบ Single Page App สำหรับ [Social Media Downloader API](https://github.com/nousresearch/social-downloader)  
พัฒนาให้คุณพ่อเลี้ยงต้อม 💙

![tech: HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat&logo=html5&logoColor=white)
![tech: Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=flat&logo=tailwind-css&logoColor=white)
![tech: Vanilla JS](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black)

---

## 📸 หน้าตา

- Dark theme ทันสมัย สีสันสวยงาม
- รองรับ YouTube, TikTok, Instagram, Twitter/X, Facebook
- Responsive — ใช้ได้ทั้ง PC และมือถือ
- ภาษาไทย 100%

## 🚀 วิธีใช้ (Production)

ระบบถูกรวมเป็น **Gateway Server ตัวเดียว** ที่ port **8080**:
- เสิร์ฟ Frontend (static files)
- พร้อม proxy `/api/*` ไปยัง Backend (port 8000)

### เปิดทั้งหมดครั้งเดียว:

```bash
cd /opt/data/projects/social-downloader
bash start.sh
```

หรือเปิดทีละตัว:

```bash
# Terminal 1: Backend
cd /opt/data/projects/social-downloader/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Gateway (Frontend + API Proxy)
cd /opt/data/projects/social-downloader/frontend
source ../backend/.venv/bin/activate
python server.py
```

แล้วเปิด `http://198.23.244.241:8080` ใน browser

### ปิดระบบ:
```bash
bash /opt/data/projects/social-downloader/stop.sh
```

---

## 🏗️ Gateway Architecture

```
Browser ──► :8080 (Gateway Server)
                ├── /index.html  → static file
                ├── /style.css   → static file
                ├── /api/platforms  → proxy ──► localhost:8000 (FastAPI Backend)
                ├── /api/info       → proxy ──► localhost:8000
                └── /api/download   → proxy ──► localhost:8000
```

ประโยชน์:
- **Single port** — เปิด firewall แค่ port 8080
- **No CORS** — frontend และ API อยู่ origin เดียวกัน
- **SPA fallback** — URL ที่ไม่มีไฟล์จะคืน `index.html`

## 🚀 วิธีใช้ (Dev — แยกกันรัน)

สำหรับ development ที่แยก frontend/backend:

```bash
# Terminal 1: Backend API
cd /opt/data/projects/social-downloader/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend static server
cd /opt/data/projects/social-downloader/frontend
python3 -m http.server 8080 --bind 0.0.0.0
```

> ⚠️ ในโหมด dev (`API_BASE = 'http://localhost:8000'`) — ต้องเปิด frontend และ backend พร้อมกัน  
> ในโหมด production (`API_BASE = ''` — relative URL) — ใช้ Gateway Server

## 🔄 Auto-start (survive restart)

เพิ่มใน `.bashrc` หรือรัน:
```bash
bash /opt/data/projects/social-downloader/startup.sh
```

หรือใช้ Hermes background process:
```python
terminal(command="cd /opt/data/projects/social-downloader/frontend && source ../backend/.venv/bin/activate && python server.py", background=True)
```

## 📡 API Endpoints ที่ใช้

| Method | Endpoint | คำอธิบาย |
|--------|----------|----------|
| `POST` | `/api/info` | ดึงข้อมูล media (title, thumbnail, duration, ฯลฯ) |
| `POST` | `/api/download` | ดาวน์โหลดไฟล์ media |
| `GET`  | `/api/platforms` | รายชื่อ platform ที่รองรับ |

Frontend ส่ง request เป็น JSON: `{ "url": "https://..." }`

## 🛠️ เทคโนโลยี

- **HTML5** + **CSS3** (Tailwind CSS ผ่าน CDN)
- **JavaScript** (Vanilla — ไม่มี framework)
- **Font:** Noto Sans Thai (Google Fonts)
- **Gateway:** FastAPI + uvicorn (รันที่ port 8080)
- **Backend:** FastAPI + yt-dlp (รันที่ port 8000)

## 🎯 Platform ที่รองรับ

| Platform | ไอคอน | คุณภาพสูงสุด | หมายเหตุ |
|----------|-------|-------------|----------|
| YouTube | ▶️ | 8K | DASH formats, playlist |
| TikTok | 🎵 | 1080p | No watermark |
| Instagram | 📸 | 1080p | Posts & Reels |
| Twitter / X | 🐦 | 1080p | 3 backend modes |
| Facebook | 👍 | 1080p | Watch & Reels |

## ⚠️ ข้อควรระวัง

- เครื่องมือนี้ใช้ **yt-dlp** ซึ่ง reverse-engineer internal APIs — อาจผิด ToS ของ platform
- **สำหรับใช้ส่วนตัวเท่านั้น** — ห้ามใช้ในเชิงพาณิชย์
- **เนื้อหาที่มีลิขสิทธิ์** — ผู้ใช้ต้องรับผิดชอบเอง

## 📁 โครงสร้างไฟล์

```
/opt/data/projects/social-downloader/
├── start.sh              # เปิดระบบทั้งหมด (backend + gateway)
├── stop.sh               # ปิดระบบทั้งหมด
├── startup.sh            # Auto-start script สำหรับ .bashrc
├── logs/                 # Log files
├── backend/
│   ├── main.py           # FastAPI Backend (port 8000)
│   ├── requirements.txt
│   └── .venv/            # Python virtual environment
├── frontend/
│   ├── index.html        # Single Page App (ไฟล์เดียว)
│   ├── server.py         # Gateway server (port 8080) — serve frontend + proxy API
│   └── README.md         # เอกสารนี้
└── docs/
```

## 🧑‍💻 พัฒนาโดย

Nous Research — สำหรับคุณพ่อเลี้ยงต้อม 💙
