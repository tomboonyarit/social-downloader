"""
Unified Gateway Server
======================
Serves the frontend (static files) on port 8080 AND
proxies /api/* requests to the backend on port 8000.

This provides a single port (8080) so the user only needs
to open one firewall port and there are no CORS issues.

Usage:
    cd /opt/data/projects/social-downloader/frontend
    python server.py
    # or: uvicorn server:app --host 0.0.0.0 --port 8080
"""

import io
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
FRONTEND_DIR = Path(__file__).parent.resolve()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8443"))
SSL_DIR = Path(__file__).parent.parent / "ssl"
SSL_CERT = os.environ.get("SSL_CERT", str(SSL_DIR / "server.crt"))
SSL_KEY = os.environ.get("SSL_KEY", str(SSL_DIR / "server.key"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("gateway")

app = FastAPI(title="Social Downloader Gateway")

# ---------------------------------------------------------------------------
# Helper: proxy request to backend
# ---------------------------------------------------------------------------

async def _proxy(request: Request, path: str) -> Response:
    """Forward a request to the backend and return its response."""
    target_url = f"{BACKEND_URL}/{path}"
    # Rebuild the query string
    query = request.url.query
    if query:
        target_url += f"?{query}"

    # Read the request body
    body = await request.body()

    # Build the upstream request
    upstream = urllib.request.Request(
        url=target_url,
        data=body if body else None,
        headers=dict(request.headers),
        method=request.method,
    )

    try:
        with urllib.request.urlopen(upstream, timeout=60) as resp:
            upstream_body = resp.read()
            return Response(
                content=upstream_body,
                status_code=resp.status,
                headers={
                    "content-type": resp.headers.get("content-type", "application/json"),
                    "content-length": str(len(upstream_body)),
                },
            )
    except urllib.error.HTTPError as e:
        # Forward error responses from the backend as-is
        error_body = e.read()
        return Response(
            content=error_body,
            status_code=e.code,
            headers={
                "content-type": e.headers.get("content-type", "application/json"),
                "content-length": str(len(error_body)),
            },
        )
    except urllib.error.URLError as e:
        log.error("Backend unreachable: %s", e)
        return PlainTextResponse(
            content=f"Backend at {BACKEND_URL} is unreachable: {e.reason}",
            status_code=502,
        )


# ---------------------------------------------------------------------------
# API proxy routes — these MUST be registered before the static file catch-all
# ---------------------------------------------------------------------------

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def api_proxy(path: str, request: Request):
    return await _proxy(request, f"api/{path}")


@app.api_route("/", methods=["GET", "HEAD"])
async def api_root(request: Request):
    # Proxy / to backend (returns JSON service info)
    return await _proxy(request, "")


# ---------------------------------------------------------------------------
# Static file serving — catch-all for frontend assets
# ---------------------------------------------------------------------------

# MIME types for common frontend extensions
MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
}


@app.get("/{path:path}")
async def serve_frontend(path: str):
    # Normalise path
    path = path.lstrip("/") or "index.html"

    # Security: prevent directory traversal
    filepath = (FRONTEND_DIR / path).resolve()
    if not str(filepath).startswith(str(FRONTEND_DIR)):
        return PlainTextResponse("Forbidden", status_code=403)

    if filepath.is_file():
        ext = filepath.suffix.lower()
        media_type = MIME_MAP.get(ext, "application/octet-stream")
        return FileResponse(filepath, media_type=media_type)

    # SPA fallback: return index.html for unknown paths
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index, media_type="text/html; charset=utf-8")

    return PlainTextResponse("Not Found", status_code=404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    log.info("Starting HTTPS gateway on %s:%s", HOST, PORT)
    log.info("Backend: %s", BACKEND_URL)
    log.info("Frontend: %s", FRONTEND_DIR)
    log.info("SSL Cert: %s", SSL_CERT)
    log.info("SSL Key:  %s", SSL_KEY)
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        ssl_certfile=SSL_CERT,
        ssl_keyfile=SSL_KEY,
        log_level="info",
    )
