from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Backend v12.0")
executor = ThreadPoolExecutor(max_workers=10)

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
    # Hum 'ios' aur 'android' clients use karenge jo Vercel par block nahi hote
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "format": "best",
        "extractor_args": {
            'youtube': {
                'player_client': ['ios', 'android'],
                'po_token': ['web+generated']
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result:
                raise Exception("No data found")
            return result
    except Exception as e:
        raise Exception(str(e))

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        formats = info.get("formats", [])
        
        for f in formats:
            f_url = f.get("url")
            if not f_url or "manifest" in f_url: continue # Skip broken links
            
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

# Vercel needs the 'app' object
