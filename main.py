from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import asyncio
import os
import tempfile
import subprocess
import sys
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Dict, Any

app = FastAPI(title="SaveMedia Verceal Optimized")
executor = ThreadPoolExecutor(max_workers=3)

# --- CORS Settings ---
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
    """
    YouTube extraction with multiple fallback clients
    Verceal par chalne ke liye special handling
    """
    
    # Clean URL
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)', url)
    if video_id_match:
        video_id = video_id_match.group(1)
        clean_url = f'https://www.youtube.com/watch?v={video_id}'
    else:
        clean_url = url
    
    # Cookies handling
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    temp_cookie_path = None
    
    if cookies_content and len(cookies_content.strip()) > 10:
        try:
            fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, 'w') as f:
                f.write(cookies_content.strip())
        except:
            pass

    # MULTIPLE CLIENT CONFIGURATIONS - Try each until one works
    clients = [
        {
            "name": "ios",
            "opts": {
                "quiet": True,
                "no_warnings": True,
                "cookiefile": temp_cookie_path,
                "socket_timeout": 30,
                "format": "best[height<=720]/best",
                "noplaylist": True,
                "extractor_args": {
                    'youtube': {
                        'player_client': ['ios'],
                    }
                },
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            }
        },
        {
            "name": "android",
            "opts": {
                "quiet": True,
                "no_warnings": True,
                "cookiefile": temp_cookie_path,
                "socket_timeout": 30,
                "format": "best[height<=720]/best",
                "noplaylist": True,
                "extractor_args": {
                    'youtube': {
                        'player_client': ['android'],
                    }
                },
                "user_agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            }
        },
        {
            "name": "web_safari",
            "opts": {
                "quiet": True,
                "no_warnings": True,
                "cookiefile": temp_cookie_path,
                "socket_timeout": 30,
                "format": "best[height<=720]/best",
                "noplaylist": True,
                "extractor_args": {
                    'youtube': {
                        'player_client': ['web_safari'],
                    }
                },
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            }
        },
        {
            "name": "web",
            "opts": {
                "quiet": True,
                "no_warnings": True,
                "cookiefile": temp_cookie_path,
                "socket_timeout": 30,
                "format": "worst",  # Worst quality but better than nothing
                "noplaylist": True,
                "extractor_args": {
                    'youtube': {
                        'player_client': ['web'],
                        'skip': ['hls', 'dash'],  # Skip problematic formats
                    }
                },
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }
        }
    ]
    
    last_error = None
    
    for client in clients:
        try:
            with yt_dlp.YoutubeDL(client["opts"]) as ydl:
                result = ydl.extract_info(clean_url, download=False)
                
                if result and isinstance(result, dict):
                    formats = result.get("formats", [])
                    # Check if we got actual video formats (not just images)
                    video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height', 0) > 0]
                    
                    if video_formats:
                        # Success! We have video formats
                        return result
                    elif formats:
                        # Only audio formats available
                        return result
                        
        except Exception as e:
            last_error = str(e)
            continue  # Try next client
    
    # Clean up
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        try: 
            os.remove(temp_cookie_path)
        except: 
            pass
    
    # Provide helpful error
    if last_error:
        if "HTTP Error 400" in last_error or "Requested format" in last_error:
            raise Exception("YouTube is blocking this request. Try a different video or use a VPN/proxy.")
        else:
            raise Exception(f"Could not extract: {last_error[:200]}")
    else:
        raise Exception("No working client found for this video")

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
            
            format_info = {
                "format_id": f.get("format_id"),
                "ext": ext,
                "resolution": quality,
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height,
            }
            formats_data.append(format_info)
        
        formats_data.sort(key=lambda x: x['height'], reverse=True)
        formats_data = formats_data[:10]
        
        return {
            "status": "success",
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "Unknown"),
            "duration": info.get("duration"),
            "formats": formats_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "verceal-final"}

@app.options("/download")
async def options_download():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
