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
# اپنا کلاؤڈ فلیئر ورکر لنک یہاں ڈالیں (آخر میں ?url= لازمی ہو)
WORKER_PROXY = "https://white-fire-28ec.muhammadyasirkhursheedahmed.workers.dev/?url="

app = FastAPI(title="SaveMedia Ultra-Proxy Edition")
executor = ThreadPoolExecutor(max_workers=5)

# --- Restricted CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

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
        "format": "best/bestvideo+bestaudio",
        "ignoreerrors": True,
        # ورکر کو بطور پراکسی استعمال کرنا تاکہ یوٹیوب کو سرور کا IP نہ ملے
        "proxy": WORKER_PROXY, 
        "socket_timeout": 30,
        
        # Automatic PO Token Generation
        "plugin_extractors": ["get_pot"],
        "extractor_args": {
            'youtube': {
                'player_client': ['web', 'ios', 'android'],
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
                raise Exception("Data extraction failed through proxy.")
            return result
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        for f in info.get("formats", []):
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

        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats_data[:15] # ٹاپ 15 بہترین فارمیٹس
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e).split('\n')[0])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
