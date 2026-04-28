from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

# Optional: ytc for automatic cookies
try:
    import ytc
    HAS_YTC = True
except ImportError:
    HAS_YTC = False

app = FastAPI(title="SaveMedia Verceal Fixed")
executor = ThreadPoolExecutor(max_workers=3)

# CORS Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://savemedia.online",
        "https://www.savemedia.online",
        "https://ticnotester.blogspot.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except:
        return url

def sync_extract_info(url: str) -> Dict[str, Any]:
    # Extract video ID
    import re
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)', url)
    if video_id_match:
        clean_url = f'https://www.youtube.com/watch?v={video_id_match.group(1)}'
    else:
        clean_url = url

    # Base yt-dlp options with web_embedded client
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "format": "best[height<=720]/best",
        "noplaylist": True,
        "extractor_args": {
            'youtube': {
                'player_client': ['default', 'web_embedded'],  # KEY FIX
            }
        },
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    # Add cookies if available
    if HAS_YTC:
        try:
            cookies = ytc.youtube()
            if cookies:
                ydl_opts['http_headers'] = {'Cookie': cookies}
        except:
            pass

    # Also try environment cookies if set
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    if cookies_content and len(cookies_content.strip()) > 10:
        import tempfile
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())
        ydl_opts['cookiefile'] = temp_cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(clean_url, download=False)
            if result and isinstance(result, dict) and result.get("formats"):
                return result
            raise Exception("No formats found")
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise Exception("This video requires authentication. Try a different video without restrictions.")
        raise Exception(f"Extraction failed: {error_msg[:200]}")

@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)

        if not info:
            raise HTTPException(status_code=400, detail="Could not retrieve video information")

        formats = info.get("formats", [])
        if not formats:
            raise HTTPException(status_code=400, detail="No formats available")

        formats_data = []
        seen = set()

        for f in formats:
            f_url = f.get("url")
            if not f_url or f_url in seen:
                continue

            protocol = f.get("protocol", "")
            if protocol in ["m3u8_native", "m3u8"]:
                continue

            seen.add(f_url)

            height = f.get('height') or 0
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            ext = f.get("ext", "mp4")

            if height > 0:
                quality = f"{height}p"
            else:
                quality = "Audio Only" if acodec != 'none' and vcodec == 'none' else "SD"

            formats_data.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "resolution": quality,
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height,
            })

        formats_data.sort(key=lambda x: x['height'], reverse=True)

        return {
            "status": "success",
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "Unknown"),
            "duration": info.get("duration"),
            "formats": formats_data[:10]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
