pfrom fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import asyncio
import re
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import List, Dict, Any

# --- FastAPI App Setup ---
app = FastAPI(
    title="SaveMedia Backend",
    version="2.1",
    description="Production-ready FastAPI backend for SaveMedia.online — direct downloadable formats only."
)

# --- ThreadPool for blocking yt-dlp calls ---
executor = ThreadPoolExecutor(max_workers=10)

# --- Restricted CORS setup ---
allowed_origins = [
    "https://savemedia.online",
    "https://www.savemedia.online",
    "https://ticnotester.blogspot.com",
    # "http://localhost:8080", # Uncomment for local testing
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
    """SSRF Protection: Block internal/metadata URLs"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return False
        blocked_hosts = ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"]
        if parsed.hostname in blocked_hosts:
            return False
        if parsed.hostname and (parsed.hostname.startswith("10.") or parsed.hostname.startswith("192.168.") or parsed.hostname.startswith("172.16.")):
            return False
        return True
    except:
        return False

def safe_filename(s: str) -> str:
    """Remove illegal characters for filenames"""
    s = re.sub(r'[\\/*?:"<>|]', "", s)
    return s.strip()[:150] # Limit length

def add_force_download_param(original_url: str) -> str:
    """Add mime=application/octet-stream to force download on mobile"""
    try:
        parsed_url = urlparse(original_url)
        query_params = parse_qs(parsed_url.query)
        query_params['mime'] = ['application/octet-stream']
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))
    except Exception:
        return original_url

def sync_extract_info(url: str) -> Dict[str, Any]:
    """Blocking yt-dlp call - run this in ThreadPool"""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "socket_timeout": 12,
        "source_address": "0.0.0.0", # Force IPv4
        "extractor_args": {
            'youtube': {
                'player_client': ['android', 'web'], # Bypass some blocks
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def parse_resolution(f: Dict) -> int:
    """Extract height for sorting. Returns 0 if not found"""
    if f.get('height'):
        return int(f['height'])
    res = f.get('resolution', '0p')
    if 'x' in res: # 1920x1080 format
        try:
            return int(res.split('x')[1])
        except:
            return 0
    return int(res.replace('p', '')) if res.replace('p', '').isdigit() else 0

# --- Root route ---
@app.get("/")
def home():
    return {"message": "✅ SaveMedia Backend v2.1 running successfully!"}

# --- Health check for Oracle/Fly.io ---
@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- Main Download Endpoint ---
@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL to extract downloadable info")):
    # 1. SSRF Validation
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid or blocked URL")

    loop = asyncio.get_event_loop()
    try:
        # 2. Run blocking yt-dlp in ThreadPool to avoid server freeze
        info = await loop.run_in_executor(executor, sync_extract_info, url)

        video_title = safe_filename(info.get("title", "downloaded_file"))
        progressive_formats: List[Dict] = []

        # 3. Filter only progressive formats (video+audio combined)
        for f in info.get("formats", []):
            original_url = f.get("url")
            if not original_url:
                continue

            # Progressive = has both audio and video
            if f.get("acodec")!= "none" and f.get("vcodec")!= "none":
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
            raise HTTPException(
                status_code=404,
                detail="No direct downloadable formats found. Video may be DASH-only."
            )

        # 4. Sort by resolution - highest first
        progressive_formats.sort(key=lambda x: x['height'], reverse=True)

        # Remove 'height' key before sending response
        for f in progressive_formats:
            del f['height']

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
        # Clean up common yt-dlp errors for user
        if "Private video" in error_msg:
            error_msg = "This video is private"
        elif "Video unavailable" in error_msg:
            error_msg = "Video is unavailable or removed"
        elif "Sign in to confirm" in error_msg:
            error_msg = "Age-restricted or sign-in required video"
        elif "Unsupported URL" in error_msg:
            error_msg = "Unsupported website or invalid URL"

        raise HTTPException(status_code=400, detail=f"Error: {error_msg}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)[:100]}")

# --- Run Server ---
if __name__ == "__main__":
    # Oracle/Fly.io پر چلانے کے لیے
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
