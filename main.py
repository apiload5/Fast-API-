from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

# --- Configuration ---
# Agar worker 400 error de raha he to use temporary empty rakhen: WORKER_PROXY = ""
WORKER_PROXY = "https://white-fire-28ec.muhammadyasirkhursheedahmed.workers.dev/?url="

app = FastAPI(title="SaveMedia Ultra Backend v10.2")
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
    # 1. Cookies Cleanup & Setup
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # 2. Advanced Multi-Strategy (No-Proxy First)
    # Pehle direct mobile client try karenge kyunke is pe proxy ki zaroorat nahi parti
    options_list = [
        # Strategy 1: Direct (Android/iOS) - Most Reliable
        {
            "format": "best", 
            "extractor_args": {
                'youtube': {
                    'player_client': ['android', 'ios'],
                    'po_token': ['web+generated']
                }
            },
        },
        # Strategy 2: Proxy Fallback (Agar direct block ho jaye)
        {
            "proxy": WORKER_PROXY if WORKER_PROXY else None,
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
        # Agar proxy set nahi he to strategy skip karein
        if opts.get("proxy") == "": continue

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": temp_cookie_path,
            "socket_timeout": 25,
            "nocheckcertificate": True,
            "check_formats": False, 
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        }
        common_opts.update(opts)

        try:
            with yt_dlp.YoutubeDL(common_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                if result:
                    break 
        except Exception as e:
            last_error = str(e).split('\n')[0]
            continue

    # Cleanup
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        try: os.remove(temp_cookie_path)
        except: pass

    if not result:
        # Agar proxy ne 400 error dia he to detail message
        raise Exception(f"Extraction failed. Possible Proxy/Token Issue: {last_error}")
    
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
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": f"{height}p" if height else "SD/Audio",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

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
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
