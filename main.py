from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Final v12.0")
executor = ThreadPoolExecutor(max_workers=5)

# --- CORS Settings ---
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

# --- Helper Functions ---
def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: 
        return url

def upgrade_yt_dlp():
    """Auto-upgrade yt-dlp to latest version"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def sync_extract_info(url: str) -> Dict[str, Any]:
    # Auto-upgrade on first run (Verceal compatibility)
    upgrade_yt_dlp()
    
    # Cookies handling for Verceal
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # OPTIMIZED CONFIGURATION FOR VERCEL
    # Verceal has limited resources, so we use multiple client fallbacks
    ydl_opts = {
        "quiet": True,
        "no_warnings": False,
        "cookiefile": temp_cookie_path,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "verbose": False,
        "format": "best[height<=1080]/best",  # Limit to 1080p for speed
        "noplaylist": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "extractor_args": {
            'youtube': {
                # Try multiple clients in order - one will work [citation:4]
                'player_client': ['android', 'ios', 'web_safari', 'web'],
                # Skip HLS/DASH formats that cause issues
                'skip': ['hls', 'dash'],
            }
        },
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result or not result.get("formats"):
                # FALLBACK: Try with web_safari only (sometimes works better) [citation:3][citation:7]
                ydl_opts["extractor_args"]['youtube']['player_client'] = ['web_safari']
                ydl_opts["format"] = "best"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    result = ydl2.extract_info(url, download=False)
            return result
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        
        # Provide helpful error messages
        if "po_token" in error_msg.lower() or "requested format" in error_msg.lower():
            raise Exception("YouTube requires updated access. Please upgrade yt-dlp with: pip install -U yt-dlp")
        elif "age" in error_msg.lower():
            raise Exception("This video is age-restricted. Cookies authentication required.")
        else:
            raise Exception(f"Extraction Error: {error_msg}")
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try: 
                os.remove(temp_cookie_path)
            except: 
                pass

# --- Main API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        formats = info.get("formats", [])
        seen_urls = set()
        
        for f in formats:
            f_url = f.get("url")
            if not f_url or f_url in seen_urls:
                continue
            
            # Skip problematic formats
            if f.get("protocol") in ["m3u8_native", "m3u8"]:
                continue
                
            seen_urls.add(f_url)
            
            height = f.get('height') or 0
            fps = f.get('fps') or 0
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            filesize = f.get('filesize') or f.get('filesize_approx')
            
            # Quality label
            if height > 0:
                quality = f"{height}p"
                if fps >= 60:
                    quality += " (60fps)"
                if vcodec and 'av01' in vcodec.lower():
                    quality += " [AV1]"
                elif vcodec and 'vp9' in vcodec.lower():
                    quality += " [VP9]"
            else:
                quality = "Audio Only" if acodec != 'none' and vcodec == 'none' else "SD/Audio"
            
            format_info = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": quality,
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height,
                "filesize": filesize,
                "vcodec": vcodec,
                "acodec": acodec
            }
            
            formats_data.append(format_info)

        # Sort by quality
        formats_data.sort(key=lambda x: (x['height'], x.get('filesize', 0)), reverse=True)

        if not formats_data:
            raise Exception("No downloadable formats found. Try a different video.")

        return {
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "formats": formats_data[:15]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint for Verceal monitoring"""
    return {"status": "healthy", "version": "12.0"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
