from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import asyncio
import re
import uvicorn
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import List, Dict, Any

# --- FastAPI App Setup ---
app = FastAPI(
    title="SaveMedia Backend",
    version="6.1",
    description="Final Version - Secure CORS & Robust Format Support"
)

# --- ThreadPool ---
executor = ThreadPoolExecutor(max_workers=10)

# --- Restricted CORS (Back Again!) ---
allowed_origins = [
    "https://savemedia.online",
    "https://www.savemedia.online",
    "https://ticnotester.blogspot.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Helper Functions ---
def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"]
    except: return False

def safe_filename(s: str) -> str:
    s = re.sub(r'[\\/*?:"<>|]', "", s)
    return s.strip()[:150]

def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: return url

def parse_resolution(f: Dict) -> int:
    h = f.get('height')
    if h: return int(h)
    res = str(f.get('resolution', '0'))
    m = re.search(r'(\d+)', res)
    return int(m.group(1)) if m else 0

# --- Core Extraction Logic ---
def sync_extract_info(url: str) -> Dict[str, Any]:
    # Vercel Settings se cookies uthana
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None

    if cookies_content:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": temp_cookie_path,
        # Sab se flexible format string
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/b*", 
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "extractor_args": {
            'youtube': {
                'player_client': ['tv', 'web', 'android'],
                'skip': ['hls', 'dash']
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

# --- Routes ---
@app.get("/")
def home():
    return {"status": "Active", "site": "savemedia.online", "version": "6.1"}

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        video_title = safe_filename(info.get("title", "video"))
        formats_data = []

        # Filter and parse formats
        for f in info.get("formats", []):
            f_url = f.get("url")
            if not f_url: continue

            # Progressive formats checking
            if f.get("vcodec") != "none" and f.get("acodec") != "none":
                res = parse_resolution(f)
                formats_data.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext", "mp4"),
                    "resolution": f"{res}p" if res else "Standard",
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "url": f_url,
                    "force_download_url": add_force_download_param(f_url),
                    "height": res
                })

        # Fallback if no progressive formats found
        if not formats_data:
            best_url = info.get("url")
            if best_url:
                formats_data.append({
                    "format_id": "best",
                    "ext": info.get("ext", "mp4"),
                    "resolution": "Best Available",
                    "url": best_url,
                    "force_download_url": add_force_download_param(best_url),
                    "height": 0
                })

        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data
        }

    except Exception as e:
        clean_error = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=clean_error)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
