from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

# --- Configuration ---
WORKER_PROXY = "https://white-fire-28ec.muhammadyasirkhursheedahmed.workers.dev/?url="

app = FastAPI(title="SaveMedia Ultra Backend v10.0")
executor = ThreadPoolExecutor(max_workers=10) # Workers thore barha diye hain speed ke liye

# --- CORS Settings ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Production mein specific domains dalein
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
    # 1. Handle Cookies from Environment Variable
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # 2. Optimized Strategies
    # Pehli koshish mobile clients se (Android/iOS) bina proxy ke, kyunke ye kam block hote hain
    # Dusri koshish Web client + Worker proxy ke sath
    options_list = [
        {
            "format": "best", 
            "extractor_args": {
                'youtube': {
                    'player_client': ['android', 'ios'],
                    'po_token': ['web+generated'] # PO Token automated generation
                }
            },
        },
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
            "socket_timeout": 20,
            "nocheckcertificate": True,
            "check_formats": False, # CRITICAL: Is se 'format not available' error solve hota hai
            "extract_flat": False,
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

    # Clean up cookie file
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
            
            # Filter: Sirf wo links jin mein video aur audio dono hon ya sirf video ho
            # Audio-only ko filter karna hai toh check 'vcodec' != 'none'
            
            height = f.get('height') or 0
            ext = f.get("ext", "mp4")
            
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "resolution": f"{height}p" if height else "Audio/SD",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # Sort: Sab se high resolution upar
        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data[:15] # Top 15 formats kafi hain
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Hosting ke liye port 8080 default rakha hai
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
