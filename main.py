from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import random
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Backend v12.1")
executor = ThreadPoolExecutor(max_workers=5)

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

def get_stable_info(url: str) -> Dict[str, Any]:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best",
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
            "DNT": "1",
        },
        "extractor_args": {
            'youtube': {
                'player_client': ['android'], 
                'player_skip': ['webpage', 'configs'],
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        # Pytube hataya gaya hai, ab sab kuch yt-dlp se handle hoga
        info = await loop.run_in_executor(executor, get_stable_info, url)
        
        formats_data = []
        for f in info.get("formats", []):
            f_url = f.get("url")
            if not f_url or "manifest" in f_url: continue
            
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
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "formats": formats_data[:15]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction Error: {str(e)}")

# Vercel entry point requirement
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
