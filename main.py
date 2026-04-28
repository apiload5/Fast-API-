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
# اپنے کلاؤڈ فلیئر ورکر کا لنک یہاں ڈالیں
WORKER_PROXY = "https://white-fire-28ec.muhammadyasirkhursheedahmed.workers.dev/?url="

app = FastAPI(title="SaveMedia Ultra Backend v10.0")
executor = ThreadPoolExecutor(max_workers=5)

# --- CORS Settings ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
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
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content)

    # دو مختلف طریقے (Strategies)
    options_list = [
        # Strategy 1: Cloudflare Worker Proxy + Web Client
        {
            "proxy": WORKER_PROXY,
            "format": "best",
            "plugin_extractors": ["get_pot"],
            "extractor_args": {
                'youtube': {
                    'player_client': ['web'], 
                    'po_token': ['web+generated']
                }
            },
        },
        # Strategy 2: Direct Server + iOS/Android Client (Afsar bhot kam block hota hai)
        {
            "format": "bestvideo+bestaudio/best",
            "plugin_extractors": ["get_pot"],
            "extractor_args": {
                'youtube': {
                    'player_client': ['ios', 'android'], 
                    'po_token': ['ios+generated']
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
            "socket_timeout": 25,
            "nocheckcertificate": True,
        }
        common_opts.update(opts)

        try:
            with yt_dlp.YoutubeDL(common_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                if result:
                    break # Agar data mil gaya to loop khatam kar do
        except Exception as e:
            last_error = str(e).split('\n')[0]
            continue

    # Clean up cookie file
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        os.remove(temp_cookie_path)

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
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": f"{height}p" if height else "Standard",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # Sort: Highest resolution at top
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
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
