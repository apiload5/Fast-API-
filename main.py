from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Final v11.0")
executor = ThreadPoolExecutor(max_workers=10)

# --- CORS Settings (Updated with your Origins) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://savemedia.online", 
        "https://www.savemedia.online", 
        "https://ticnotester.blogspot.com"
    ],
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
    # 1. Cookies Cleanup
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # 2. Strongest Extraction Settings (Anti-Block)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": temp_cookie_path,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        
        # --- CRITICAL FIXES FOR "FORMAT NOT AVAILABLE" ---
        "format": "best",            # Default to best available
        "check_formats": False,       # Do not verify links (fixes the 400/Format error)
        "noplaylist": True,
        "extract_flat": False,        # We need full format data
        
        "extractor_args": {
            'youtube': {
                'player_client': ['android', 'ios'], # Mobile is safer
                'po_token': ['web+generated']
            }
        },
        # Fixed User-Agent
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First attempt with full processing
            result = ydl.extract_info(url, download=False)
            if not result:
                raise Exception("YouTube returned empty data.")
            return result
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        raise Exception(f"Extraction Error: {error_msg}")
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try: os.remove(temp_cookie_path)
            except: pass

# --- API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        # Running in executor to prevent blocking
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        formats = info.get("formats", [])
        
        for f in formats:
            f_url = f.get("url")
            if not f_url: continue
            
            # Metadata filters
            height = f.get('height') or 0
            ext = f.get("ext", "mp4")
            
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "resolution": f"{height}p" if height else "SD/Audio",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # Sort: Highest quality first
        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data[:20]
        }
    except Exception as e:
        # CORS headers are automatically handled by FastAPI middleware
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
