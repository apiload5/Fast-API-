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
    version="2.2",
    description="Production-ready FastAPI backend for SaveMedia.online — with Cookie Support."
)

# --- ThreadPool for blocking yt-dlp calls ---
executor = ThreadPoolExecutor(max_workers=10)

# --- Restricted CORS setup ---
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
        if parsed.scheme not in ["http", "https"]:
            return False
        blocked_hosts = ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"]
        if parsed.hostname in blocked_hosts:
            return False
        return True
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
    except Exception:
        return original_url

def parse_resolution(f: Dict) -> int:
    if f.get('height'):
        return int(f['height'])
    res = f.get('resolution', '0p')
    if 'x' in res:
        try:
            return int(res.split('x')[1])
        except:
            return 0
    return int(res.replace('p', '')) if res.replace('p', '').isdigit() else 0

def sync_extract_info(url: str) -> Dict[str, Any]:
    """Blocking yt-dlp call with Environment Cookie Support"""
    
    # Vercel environment se cookies uthana
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None

    # Agar cookies maujood hain, to ek temporary file banana
    if cookies_content:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "cookiefile": temp_cookie_path, # Cookies yahan istemal ho rahi hain
        "socket_timeout": 15,
        "source_address": "0.0.0.0",
        "extractor_args": {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    finally:
        # File delete karna taaki storage saaf rahe
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

# --- Routes ---
@app.get("/")
def home():
    return {"message": "✅ SaveMedia Backend v5.1 (Cookies Enabled) running successfully!"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL")):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid or blocked URL")

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)

        video_title = safe_filename(info.get("title", "downloaded_file"))
        progressive_formats: List[Dict] = []

        for f in info.get("formats", []):
            original_url = f.get("url")
            if not original_url: continue

            if f.get("acodec") != "none" and f.get("vcodec") != "none":
                force_download_url = add_force_download_param(original_url)
                height = parse_resolution(f)

                progressive_formats.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext", "mp4"),
                    "format_note": f.get("format_note"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "url": original_url,
                    "force_download_url": force_download_url,
                    "resolution": f"{height}p" if height else f.get("resolution"),
                    "height": height,
                    "suggested_filename": f"{video_title}.{f.get('ext', 'mp4')}",
                })

        if not progressive_formats:
            raise HTTPException(status_code=404, detail="No direct downloadable formats found.")

        progressive_formats.sort(key=lambda x: x['height'], reverse=True)
        for f in progressive_formats: del f['height']

        return JSONResponse(content={
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url"),
            "formats": progressive_formats,
        })

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"Error: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)[:100]}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
