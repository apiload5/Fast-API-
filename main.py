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
    version="5.5",
    description="Secure Version — Cookies via Environment Variables"
)

# --- ThreadPool for blocking yt-dlp calls ---
executor = ThreadPoolExecutor(max_workers=10)

# --- CORS Setup ---
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
    except:
        return False

def safe_filename(s: str) -> str:
    s = re.sub(r'[\\/*?:"<>|]', "", s)
    return s.strip()[:150]

def add_force_download_param(original_url: str) -> str:
    try:
        parsed_url = urlparse(original_url)
        query_params = parse_qs(parsed_url.query)
        query_params['mime'] = ['application/octet-stream']
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))
    except:
        return original_url

def parse_resolution(f: Dict) -> int:
    if f.get('height'):
        return int(f['height'])
    res = str(f.get('resolution', '0'))
    match = re.search(r'(\d+)', res)
    return int(match.group(1)) if match else 0

def sync_extract_info(url: str) -> Dict[str, Any]:
    """Extract info using Cookies from Environment Variable"""
    
    # Vercel/System settings se cookies uthana (SAB SE SAFE TAREEKA)
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None

    if cookies_content:
        # Create a secure temporary file for the session
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "cookiefile": temp_cookie_path, 
        "format": "best", # "Format not available" error se bachne ke liye
        "socket_timeout": 20,
        "extractor_args": {
            'youtube': {
                'player_client': ['android', 'web', 'ios'],
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
        # File delete karna taaki storage saaf rahe aur security bani rahe
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

# --- Routes ---
@app.get("/")
def home():
    return {"message": "✅ SaveMedia v5.5 (Secure Mode) is running!"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL")):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid or blocked URL")

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)

        video_title = safe_filename(info.get("title", "download"))
        progressive_formats: List[Dict] = []

        # Filter for formats that have BOTH video and audio
        for f in info.get("formats", []):
            original_url = f.get("url")
            if not original_url: continue

            # Progressive formats (vcodec and acodec present)
            if f.get("acodec") != "none" and f.get("vcodec") != "none":
                height = parse_resolution(f)
                progressive_formats.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext", "mp4"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "url": original_url,
                    "force_download_url": add_force_download_param(original_url),
                    "resolution": f"{height}p" if height else "MP4",
                    "height": height,
                })

        # Fallback agar koi progressive format na mile
        if not progressive_formats:
             for f in info.get("formats", []):
                if f.get("url"):
                    progressive_formats.append({
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext", "mp4"),
                        "url": f.get("url"),
                        "force_download_url": add_force_download_param(f.get("url")),
                        "resolution": "Available",
                        "height": 0
                    })

        # Sort by resolution (Highest first)
        progressive_formats.sort(key=lambda x: x['height'], reverse=True)

        return JSONResponse(content={
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": progressive_formats,
        })

    except Exception as e:
        # Detail error message for debugging
        error_str = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"YT-DLP Error: {error_str}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
