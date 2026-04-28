from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
from pytube import YouTube
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Backend v11.0")
executor = ThreadPoolExecutor(max_workers=10)

# --- CORS Settings ---
# Yahan aapki domains allow kar di gayi hain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://savemedia.online", 
        "https://www.savemedia.online", 
        "https://ticnotester.blogspot.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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

def is_youtube(url: str) -> bool:
    domain = urlparse(url).netloc
    return 'youtube.com' in domain or 'youtu.be' in domain

# --- Extraction Logic ---
def extract_info(url: str) -> Dict[str, Any]:
    # --- YouTube Strategy: Pytube ---
    if is_youtube(url):
        try:
            yt = YouTube(url)
            formats_data = []
            # Progressive streams provide both video and audio in one file
            for stream in yt.streams.filter(progressive=True):
                res = stream.resolution or "0p"
                formats_data.append({
                    "format_id": str(stream.itag),
                    "ext": stream.mime_type.split('/')[-1],
                    "resolution": res,
                    "url": stream.url,
                    "force_download_url": add_force_download_param(stream.url),
                    "height": int(res.replace("p", ""))
                })
            
            return {
                "source": "pytube",
                "title": yt.title,
                "thumbnail": yt.thumbnail_url,
                "uploader": yt.author,
                "duration": yt.length,
                "formats": formats_data
            }
        except Exception as e:
            raise Exception(f"YouTube Error (Pytube): {str(e)}")

    # --- Other Platforms: yt-dlp (No Proxy) ---
    else:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "best",
            "nocheckcertificate": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
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
                
                return {
                    "source": "yt-dlp",
                    "title": info.get("title"),
                    "thumbnail": info.get("thumbnail"),
                    "uploader": info.get("uploader"),
                    "duration": info.get("duration"),
                    "formats": formats_data
                }
        except Exception as e:
            raise Exception(f"Platform Error (yt-dlp): {str(e)}")

# --- API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, extract_info, url)
        
        # Sort: High Quality First
        if data["formats"]:
            data["formats"].sort(key=lambda x: x.get('height', 0), reverse=True)

        return {
            "status": "success",
            "extracted_via": data["source"],
            "title": data.get("title"),
            "thumbnail": data.get("thumbnail"),
            "uploader": data.get("uploader"),
            "duration": data.get("duration"),
            "formats": data["formats"][:20]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Port 8080 use ho raha hai, aap zarurat ke mutabiq change kar sakte hain
    uvicorn.run(app, host="0.0.0.0", port=8080)
