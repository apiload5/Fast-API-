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

app = FastAPI(title="SaveMedia Ultra-Stable")

executor = ThreadPoolExecutor(max_workers=10)

# CORS Settings
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

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"]
    except: return False

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
        # سب سے اہم تبدیلی: یہ کسی بھی دستیاب فائل کو اٹھا لے گا بغیر نخرے کیے
        "format": "b/best", 
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "extractor_args": {
            'youtube': {
                # 'ios' اور 'android' کو 'web' کے ساتھ ملا کر استعمال کرنا
                'player_client': ['web', 'ios', 'android', 'tv'],
                'skip': ['hls', 'dash']
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info کو فیل نہیں ہونے دینا
            result = ydl.extract_info(url, download=False)
            if not result:
                raise Exception("Could not extract info. YouTube is blocking this request.")
            return result
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        # تمام دستیاب فارمیٹس کو دکھانا تاکہ صارف کوئی بھی ڈاؤن لوڈ کر سکے
        for f in info.get("formats", []):
            f_url = f.get("url")
            if not f_url: continue

            # ریزولیوشن نکالنے کی سادہ کوشش
            height = f.get('height') or 0
            
            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": f"{height}p" if height else "Unknown",
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height
            })

        # اگر لسٹ خالی ہو تو بنیادی ڈیٹا ڈال دیں
        if not formats_data and info.get("url"):
            formats_data.append({
                "format_id": "best",
                "ext": info.get("ext", "mp4"),
                "resolution": "Best",
                "url": info.get("url"),
                "force_download_url": add_force_download_param(info.get("url")),
                "height": 0
            })

        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "formats": formats_data
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
