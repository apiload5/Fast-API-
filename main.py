from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
import requests  # Stable proxy handling ke liye
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

# --- Configuration ---
# Aapka Cloudflare Worker Proxy
WORKER_PROXY = "https://white-fire-28ec.muhammadyasirkhursheedahmed.workers.dev/?url="

app = FastAPI(title="SaveMedia Ultra Backend v10.1")
executor = ThreadPoolExecutor(max_workers=10)

# --- CORS Settings ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Helpers ---
def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: return url

def sync_extract_info(url: str) -> Dict[str, Any]:
    # 1. Cookies extraction from Environment Variable
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # 2. Optimized Strategies (Bina kisi risky 'impersonate' target ke)
    options_list = [
        # Strategy 1: Mobile Clients (Direct, no proxy) - Best success rate
        {
            "format": "best", 
            "extractor_args": {
                'youtube': {
                    'player_client': ['android', 'ios'],
                    'po_token': ['web+generated']
                }
            },
        },
        # Strategy 2: Web Client + Cloudflare Proxy (Standard Requests)
        {
            "proxy": WORKER_PROXY,
            "format": "best",
            "extractor_args": {
                'youtube': {
                    'player_client': ['web'],
                    'po_token': ['web+generated']
                }
            },
        }
    ]

    last_error = ""
    result = None

    for opts in options_list:
        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": temp_cookie_path,
            "socket_timeout": 30,
            "nocheckcertificate": True,
            "check_formats": False, # CRITICAL: Requested format not available fix
            # Browser-like headers manually set taake impersonate ki zaroorat na pare
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        common_opts.update(opts)

        try:
            with yt_dlp.YoutubeDL(common_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                if result:
                    break 
        except Exception as e:
            # Error log cleanup
            last_error = str(e).split('\n')[0]
            continue

    # Cleanup cookie file
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        try: os.remove(temp_cookie_path)
        except: pass

    if not result:
        raise Exception(f"Extraction failed: {last_error}")
    
    return result

# --- API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        formats = info.get("formats", [])
        
        for f in formats:
            f_url = f.get("url")
            if not f_url: continue
            
            height = f.get('height') or 0
            ext = f.get("ext", "mp4")
            
            # Sirf useful formats filter kar rahe hain
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "resolution": f"{height}p" if height else "SD/Audio",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # Highest resolution first
        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data[:15]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Hosting port configuration
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
