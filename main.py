from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Ultra Final v12.0")
executor = ThreadPoolExecutor(max_workers=10)

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

# --- Helpers ---
def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: 
        return url

def sync_extract_info(url: str) -> Dict[str, Any]:
    # Cookies Cleanup
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.strip())

    # FIXED: Correct yt-dlp settings for YouTube 2024/2025
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": temp_cookie_path,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        
        # CRITICAL FIXES:
        "format": "bestvideo+bestaudio/best",  # Allow merging formats
        "noplaylist": True,
        
        # REMOVE check_formats - causes issues
        # REMOVE extract_flat - we need full data
        
        # UPDATED extractor_args for 2024/2025
        "extractor_args": {
            'youtube': {
                'skip': ['hls', 'dash'],  # Skip problematic formats
                'player_client': ['android', 'ios', 'web'],  # Try multiple clients
                'po_token': ['web+generated', 'android+generated'],  # Better PoToken handling
            }
        },
        
        # Better User-Agent
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        
        # Additional fixes
        "extract_flat": False,
        "force_generic_extractor": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result:
                raise Exception("YouTube returned empty data.")
            
            # FIX: Ensure formats exist
            if not result.get("formats"):
                # Try fallback with different settings
                ydl_opts_fallback = {
                    **ydl_opts,
                    "format": "best",
                    "extractor_args": {
                        'youtube': {
                            'player_client': ['ios'],  # iOS client works best
                            'po_token': ['ios+generated']
                        }
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl2:
                    result = ydl2.extract_info(url, download=False)
            
            return result
            
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        
        # Provide helpful error messages
        if "po_token" in error_msg.lower() or "requested format" in error_msg.lower():
            raise Exception("YouTube access requires updated configuration. Please try again.")
        else:
            raise Exception(f"Extraction Error: {error_msg}")
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try: 
                os.remove(temp_cookie_path)
            except: 
                pass

# --- API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        formats_data = []
        formats = info.get("formats", [])
        
        # Filter and process formats
        seen_urls = set()  # Avoid duplicates
        
        for f in formats:
            f_url = f.get("url")
            if not f_url or f_url in seen_urls:
                continue
            
            # Skip problematic formats
            if f.get("protocol") in ["m3u8_native", "m3u8"]:
                continue
                
            seen_urls.add(f_url)
            
            # Better resolution detection
            height = f.get('height') or 0
            fps = f.get('fps') or 0
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            
            # Determine quality label
            if height > 0:
                quality = f"{height}p"
                if fps >= 60:
                    quality += " (60fps)"
            else:
                quality = "Audio Only" if acodec != 'none' and vcodec == 'none' else "SD/Audio"
            
            format_info = {
                "format_id": f.get("format_id"),
                "ext": f.get("ext", "mp4"),
                "resolution": quality,
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "vcodec": vcodec,
                "acodec": acodec
            }
            
            formats_data.append(format_info)

        # Sort by quality
        formats_data.sort(key=lambda x: (x['height'], x.get('filesize', 0)), reverse=True)

        # Limit formats but keep best ones
        formats_data = formats_data[:25]

        if not formats_data:
            raise Exception("No downloadable formats found for this video")

        return {
            "status": "success",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "formats": formats_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
