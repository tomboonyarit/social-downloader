"""
Social Media Downloader — Backend REST API
============================================
FastAPI application using yt-dlp Python API to download media from
YouTube, TikTok, Instagram, Twitter/X, and Facebook.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000

Environment variables:
    API_KEY         — Required API key for X-API-Key header auth
    DOWNLOAD_DIR    — Directory for temporary downloads (default: ./downloads)
    MAX_CONCURRENT  — Max concurrent downloads (default: 3)
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import FastAPI, HTTPException, Depends, Header, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, HttpUrl, field_validator

# ---------------------------------------------------------------------------
# yt-dlp — must be importable; we ship requirements.txt with it
# ---------------------------------------------------------------------------
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, SameFileError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("social-downloader")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# If API_KEY env is set, use it for auth; otherwise open access
API_KEY = os.environ.get("API_KEY")

SUPPORTED_PLATFORMS = [
    {
        "id": "youtube",
        "name": "YouTube",
        "url_pattern": "youtube.com/*, youtu.be/*",
        "max_quality": "8K",
        "status": "✅ Excellent",
        "notes": "Best-in-class support. DASH formats up to 8K.",
    },
    {
        "id": "tiktok",
        "name": "TikTok",
        "url_pattern": "tiktok.com/@*/video/*, vm.tiktok.com/*",
        "max_quality": "1080p",
        "status": "✅ Good",
        "notes": "play_addr = no watermark. Cookies may be needed for datacenter IPs.",
    },
    {
        "id": "instagram",
        "name": "Instagram",
        "url_pattern": "instagram.com/p/*, instagram.com/reel/*",
        "max_quality": "1080p",
        "status": "⚠️ Partial",
        "notes": "User extractor broken. Use single post/reel URLs. Cookies required for stories.",
    },
    {
        "id": "twitter",
        "name": "Twitter / X",
        "url_pattern": "twitter.com/*/status/*, x.com/*/status/*",
        "max_quality": "1080p",
        "status": "✅ Good",
        "notes": "3 backends: GraphQL, Legacy REST, Syndication (no auth fallback).",
    },
    {
        "id": "facebook",
        "name": "Facebook",
        "url_pattern": "facebook.com/watch/*, fb.watch/*, facebook.com/reel/*",
        "max_quality": "1080p",
        "status": "⚠️ Fragile",
        "notes": "Login support removed Dec 2025. Use --impersonate + cookies.",
    },
    {
        "id": "bigo",
        "name": "Bigo TV",
        "url_pattern": "bigo.tv/*",
        "max_quality": "1080p",
        "status": "✅ Good",
        "notes": "Live streams & VODs. Check if stream is live before download.",
    },
]

FORMAT_SPEC = "bv*+ba/b"  # Best video + best audio, fallback to best single file

# ---------------------------------------------------------------------------
# Rate limiter — simple asyncio queue-based throttle
# ---------------------------------------------------------------------------
class DownloadQueue:
    """Semaphore-based concurrency limiter for downloads."""

    def __init__(self, max_concurrent: int = 3):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent

    @property
    def available(self) -> int:
        return self._max - (self._max - self._sem._value)  # approximate

    async def acquire(self) -> None:
        await self._sem.acquire()

    def release(self) -> None:
        self._sem.release()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class DownloadRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class InfoRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class PlatformInfo(BaseModel):
    id: str
    name: str
    url_pattern: str
    max_quality: str
    status: str
    notes: str


class FormatInfo(BaseModel):
    format_id: str
    ext: str
    resolution: Optional[str] = None
    filesize: Optional[int] = None
    filesize_approx: Optional[int] = None
    tbr: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    note: Optional[str] = None


class MediaInfo(BaseModel):
    title: str
    url: str
    webpage_url: str
    extractor: str
    extractor_key: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None
    uploader_url: Optional[str] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    formats: list[FormatInfo] = []
    best_format: Optional[FormatInfo] = None
    platform: Optional[str] = None


class DownloadResult(BaseModel):
    success: bool
    filename: Optional[str] = None
    title: Optional[str] = None
    ext: Optional[str] = None
    filesize: Optional[int] = None
    platform: Optional[str] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_download_dir() -> Path:
    """Return a session-scoped temp directory for downloads."""
    d = os.environ.get("DOWNLOAD_DIR")
    if d:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return p
    # Use a persistent temp dir per app start
    base = Path(tempfile.gettempdir()) / "social-downloader"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_ytdl_op(logged_in: bool = False) -> dict:
    """Return base yt-dlp options for the Python API."""
    opts = {
        "format": FORMAT_SPEC,
        "merge_output_format": "mp4",
        "outtmpl": str(_get_download_dir() / "%(id)s_%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": False,
        "extract_flat": False,
        "ignoreerrors": False,
        "nocheckcertificate": True,
        "retries": 10,
        "file_access_retries": 10,
        "retry_sleep": "linear=1:2:10",
        # Polite scraping defaults from research
        "sleep_interval": 5,
        "max_sleep_interval": 15,
        "sleep_requests": 1.0,
        # TLS impersonation — use env YP_IMPERSONATE to enable
        # e.g. YP_IMPERSONATE=chrome-99  or  chrome-124, safari-ios
        # Geo-bypass
        "xff": "default",
        "extractor_args": {},
    }
    # Allow impersonation via env var (not always available without curl_cffi)
    imp_target = os.environ.get("YP_IMPERSONATE")
    if imp_target:
        opts["impersonate"] = imp_target
    # Add cookies from browser if available (common browsers)
    if logged_in:
        opts["cookies_from_browser"] = ("firefox",)

    return opts


def _extract_platform(url: str) -> str:
    """Heuristic: guess platform from URL."""
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "instagram.com" in url_lower:
        return "instagram"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    if "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        return "facebook"
    if "bigo.tv" in url_lower:
        return "bigo"
    return "unknown"


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters problematic for filenames."""
    replacements = {
        "/": "_",
        "\\": "_",
        ":": " -",
        "*": "",
        "?": "",
        '"': "",
        "<": "",
        ">": "",
        "|": "",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name.strip() or "download"


def _format_formats(ydl_info: dict) -> list[FormatInfo]:
    """Extract useful format info from yt-dlp metadata."""
    formats = []
    seen = set()
    for f in ydl_info.get("formats", []):
        fid = f.get("format_id", "")
        if fid in seen:
            continue
        seen.add(fid)
        formats.append(
            FormatInfo(
                format_id=fid,
                ext=f.get("ext", "?"),
                resolution=f.get("resolution"),
                filesize=f.get("filesize"),
                filesize_approx=f.get("filesize_approx"),
                tbr=f.get("tbr"),
                vcodec=f.get("vcodec"),
                acodec=f.get("acodec"),
                width=f.get("width"),
                height=f.get("height"),
                fps=f.get("fps"),
                note=f.get("format_note"),
            )
        )
    return formats


def _best_format(ydl_info: dict) -> Optional[FormatInfo]:
    """Identify the best combined format from metadata."""
    # yt-dlp puts the selected format in request_formats or format_id
    selected_id = ydl_info.get("format_id", "")
    all_fmts = _format_formats(ydl_info)
    for f in all_fmts:
        if f.format_id == selected_id:
            return f
    # Fallback: the first format (typically best)
    if all_fmts:
        return all_fmts[0]
    return None


# ---------------------------------------------------------------------------
# App & Lifespan
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.queue: DownloadQueue = DownloadQueue(
            max_concurrent=int(os.environ.get("MAX_CONCURRENT", "3"))
        )
        self.download_dir: Path = _get_download_dir()


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    log.info(
        "Social Media Downloader API starting — "
        f"max concurrent: {state.queue._max}, "
        f"download dir: {state.download_dir}"
    )
    # Clean stale downloads from previous runs
    for f in state.download_dir.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass
    yield
    # Shutdown: clean up
    log.info("Shutting down — cleaning download directory.")
    shutil.rmtree(state.download_dir, ignore_errors=True)


app = FastAPI(
    title="Social Media Downloader API",
    description=__doc__,
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow frontend from any origin in dev; lock down in production
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Key Auth
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("API_KEY")


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Dependency: verify X-API-Key header matches configured key."""
    if not API_KEY:
        # No key configured → allow all
        return True
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Provide a valid API key to access this API.",
        )
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key. Check your X-API-Key header value.",
        )
    return True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Root"])
async def root():
    """Health-check / welcome endpoint."""
    return {
        "service": "Social Media Downloader API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get(
    "/api/platforms",
    response_model=list[PlatformInfo],
    dependencies=[Depends(verify_api_key)],
    tags=["Platforms"],
    summary="List supported platforms",
    description="Returns a list of all social media platforms supported by this API.",
)
async def get_platforms():
    """Return list of supported platforms with status and metadata."""
    return SUPPORTED_PLATFORMS


@app.post(
    "/api/info",
    response_model=MediaInfo,
    dependencies=[Depends(verify_api_key)],
    tags=["Media Info"],
    summary="Get media information before downloading",
    description=(
        "Given a social media URL, fetch metadata (title, duration, "
        "available formats, etc.) without downloading the file."
    ),
)
async def get_info(request: InfoRequest):
    """Fetch metadata for a URL without downloading the media file."""
    url = request.url
    platform = _extract_platform(url)

    log.info("Fetching info for URL: %s (platform: %s)", url, platform)

    opts = _get_ytdl_op(logged_in=False)
    opts["skip_download"] = True  # Important: don't download
    opts["extract_flat"] = False

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract_info, url, opts)
    except (DownloadError, ExtractorError) as e:
        log.warning("yt-dlp extract failed: %s", str(e))
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract info: {_clean_error(str(e))}",
        )
    except Exception as e:
        log.error("Unexpected error extracting info: %s", type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error extracting media info: {_clean_error(str(e))}",
        )

    # Build response
    formats = _format_formats(info)
    best = _best_format(info)

    return MediaInfo(
        title=info.get("title", "Untitled"),
        url=url,
        webpage_url=info.get("webpage_url", url),
        extractor=info.get("extractor", ""),
        extractor_key=info.get("extractor_key", ""),
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        description=info.get("description"),
        uploader=info.get("uploader"),
        uploader_url=info.get("uploader_url"),
        upload_date=info.get("upload_date"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        formats=formats,
        best_format=best,
        platform=platform,
    )


def _extract_info(url: str, opts: dict) -> dict:
    """Synchronous yt-dlp extraction runner (called via executor)."""
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_media(url: str, opts: dict) -> dict:
    """Synchronous yt-dlp download runner (called via executor)."""
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True)


@app.post(
    "/api/download",
    dependencies=[Depends(verify_api_key)],
    tags=["Download"],
    summary="Download media from URL",
    description=(
        "Download a video/image from a supported social media URL. "
        "The file is streamed back to the client. "
        "Uses best video+audio format (merged via ffmpeg)."
    ),
)
async def download_media(request: DownloadRequest):
    """Download media from a social media URL and return the file."""
    url = request.url
    platform = _extract_platform(url)

    log.info("Download request for URL: %s (platform: %s)", url, platform)

    # Check concurrency limit
    if state.queue.available <= 0:
        log.warning("Queue full — rejecting download for %s", url)
        raise HTTPException(
            status_code=429,
            detail=(
                "Server is busy. Too many concurrent downloads. "
                f"Max concurrent: {state.queue._max}. Try again shortly."
            ),
        )

    await state.queue.acquire()
    try:
        result = await _do_download(url, platform)
    finally:
        state.queue.release()

    if result.success and result.filename:
        filepath = Path(result.filename)
        if not filepath.exists():
            raise HTTPException(
                status_code=500,
                detail="Download completed but file not found on server.",
            )

        # Determine media type
        ext = result.ext or filepath.suffix.lstrip(".") or "mp4"
        media_type_map = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mkv": "video/x-matroska",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
            "wav": "audio/wav",
        }
        media_type = media_type_map.get(ext, "application/octet-stream")

        # Stream the file back, then schedule cleanup
        sanitized = _sanitize_filename(result.title or "download")
        download_name = f"{sanitized}.{ext}"

        return FileResponse(
            path=str(filepath),
            media_type=media_type,
            filename=download_name,
            headers={
                "X-Download-Platform": platform,
                "X-Download-Size": str(result.filesize or 0),
            },
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Download failed for unknown reason.",
        )


async def _do_download(url: str, platform: str) -> DownloadResult:
    """Execute download using yt-dlp Python API in thread pool."""
    opts = _get_ytdl_op(logged_in=False)
    # Generate a unique output template to avoid collisions
    unique_id = uuid.uuid4().hex[:12]
    outdir = _get_download_dir()
    opts["outtmpl"] = str(outdir / f"{unique_id}_%(title)s.%(ext)s")

    log.info("Starting download: %s", url)

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _download_media, url, opts)
    except (DownloadError, ExtractorError) as e:
        log.warning("yt-dlp download failed: %s", _clean_error(str(e)))
        return DownloadResult(
            success=False,
            error=f"Download/extraction failed: {_clean_error(str(e))}",
        )
    except Exception as e:
        log.error("Unexpected download error: %s", type(e).__name__, exc_info=True)
        return DownloadResult(
            success=False,
            error=f"Unexpected server error: {_clean_error(str(e))}",
        )

    # Find the downloaded file
    title = info.get("title", "Untitled")
    ext = info.get("ext", "mp4")
    filesize = info.get("filesize") or info.get("filesize_approx")

    # yt-dlp may have created the file in our outdir
    downloaded_path = None
    for f in outdir.iterdir():
        if f.name.startswith(unique_id):
            downloaded_path = f
            break

    if not downloaded_path:
        # Fallback: search by sanitized title
        sanitized_title = _sanitize_filename(title)
        for f in outdir.iterdir():
            if sanitized_title in f.name:
                downloaded_path = f
                break

    if not downloaded_path:
        # Last resort: most recent file in outdir
        files = sorted(outdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            downloaded_path = files[0]

    if not downloaded_path or not downloaded_path.exists():
        return DownloadResult(
            success=False,
            error="Download completed but output file could not be located.",
        )

    actual_size = downloaded_path.stat().st_size
    actual_ext = downloaded_path.suffix.lstrip(".") or ext

    return DownloadResult(
        success=True,
        filename=str(downloaded_path),
        title=title,
        ext=actual_ext,
        filesize=actual_size,
        platform=platform,
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    log.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.environ.get("DEBUG") else None,
        },
    )


def _clean_error(msg: str) -> str:
    """Shorten verbose yt-dlp error messages for API responses."""
    if not msg:
        return "Unknown error"
    # Remove excessive traceback-like prefixes
    cleaned = msg.split("\n")[0][:200]
    return cleaned


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
