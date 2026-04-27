from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any, List

# --- App Setup ---
app = FastAPI(title="SaveMedia Backend v8.0 - Format-Free Mode")
executor = ThreadPoolExecutor(max_workers=5)

# --- Restricted CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Helper ---
def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: return url

def sync_extract_info(url: str) -> Dict[str, Any]:
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
        
        # --- SOLUTION: Error se bachne ke liye format ko 'best' rakhen ---
        "format": "best/bestvideo+bestaudio", 
        "ignoreerrors": True,
        "socket_timeout": 30,
        
        # PO Token Automation
        "plugin_extractors": ["get_pot"],
        "extractor_args": {
            'youtube': {
                'player_client': ['web', 'ios', 'tv'],
                'skip': ['hls', 'dash'],
                'po_token': ['web+generated', 'ios+generated']
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result:
                raise Exception("YouTube is blocking this request. Check your cookies.")
            return result
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

# --- Routes ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        # Jo bhi formats available hain unki list banana
        formats = info.get("formats", [])
        
        for f in formats:
            f_url = f.get("url")
            if not f_url: continue
            
            # Resolution handling
            height = f.get('height') or 0
            
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": f"{height}p" if height else "Standard",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # Agar progressive formats na milen to single best output de do
        if not formats_data:
             formats_data.append({
                "format_id": "best",
                "ext": info.get("ext", "mp4"),
                "resolution": "Best Available",
                "url": info.get("url"),
                "force_download_url": add_force_download_param(info.get("url")),
                "height": 0
            })

        # Highest resolution first
        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data
        }
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"Error: {error_msg}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
