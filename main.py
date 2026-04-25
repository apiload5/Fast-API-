from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
import random
import requests
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.3")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Proxy Configuration
PROXY_LIST = []
ENV_PROXIES = os.getenv("PROXY_LIST", "")
if ENV_PROXIES:
    PROXY_LIST.extend([p.strip() for p in ENV_PROXIES.split(',') if p.strip()])

ACTIVE_PROXIES = PROXY_LIST
FAILED_PROXIES = set()

def get_working_proxy():
    """Get a working proxy"""
    available_proxies = [p for p in ACTIVE_PROXIES if p not in FAILED_PROXIES]
    if not available_proxies:
        return None
    return random.choice(available_proxies)

def setup_cookies():
    """Setup cookie file from environment variable"""
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
            return cookie_path
        except Exception as e:
            logger.error(f"Cookie setup failed: {e}")
    return None

@app.get("/download")
async def extract_video(
    url: str = Query(...), 
    format_code: Optional[str] = Query(None)  # Allow specific format code
):
    cookie_path = setup_cookies()
    proxy_url = get_working_proxy()
    
    # Dynamic format selection based on what's available
    if format_code:
        format_spec = format_code
    else:
        # Try multiple fallback formats in order of preference
        format_spec = "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]/best"
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": cookie_path if cookie_path and os.path.exists(cookie_path) else None,
        "user_agent": random.choice([
            "com.google.android.youtube/19.12.35 (Linux; U; Android 14; en_US; Pixel 7 Pro) gzip",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        ]),
        "format": format_spec,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage"],
            }
        }
    }
    
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting info for: {url}")
            
            # First, get all available formats
            info = ydl.extract_info(url, download=False)
            
            # Process all available video formats
            formats = []
            seen_resolutions = set()
            
            for f in info.get("formats", []):
                # Filter for video formats only
                if f.get("vcodec") == "none":
                    continue
                
                # Get resolution
                height = f.get("height")
                width = f.get("width")
                if height:
                    resolution = f"{height}p"
                else:
                    resolution = f.get("format_note") or "Unknown"
                
                # Avoid duplicates
                if resolution in seen_resolutions:
                    continue
                seen_resolutions.add(resolution)
                
                # Get filesize
                filesize = f.get("filesize") or f.get("filesize_approx")
                
                # Create download URL
                video_url = f.get("url")
                if not video_url:
                    continue
                
                # Try to force download
                try:
                    p = urlparse(video_url)
                    q = parse_qs(p.query)
                    q['mime'] = ['application/octet-stream']
                    force_url = urlunparse(p._replace(query=urlencode(q, doseq=True)))
                except:
                    force_url = video_url
                
                formats.append({
                    "format_id": f.get("format_id"),
                    "resolution": resolution,
                    "ext": f.get("ext", "mp4"),
                    "url": video_url,
                    "force_download_url": force_url,
                    "filesize": filesize,
                    "fps": f.get("fps"),
                    "vcodec": f.get("vcodec"),
                    "acodec": f.get("acodec"),
                    "quality": height if height else 0
                })
            
            # Sort by quality (highest first)
            formats.sort(key=lambda x: x['quality'], reverse=True)
            
            # Remove quality field from response
            for f in formats:
                del f['quality']
            
            # Get best format URL for direct download
            best_format = None
            best_url = None
            
            # Try to get best mp4 format
            for f in formats:
                if f['ext'] == 'mp4' and f['resolution'].replace('p', '').isdigit():
                    best_format = f
                    best_url = f['url']
                    break
            
            if not best_url and formats:
                best_url = formats[0]['url']
                best_format = formats[0]
            
            response_data = {
                "success": True,
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "url": best_url,  # Best quality URL
                "formats": formats,
                "format_count": len(formats)
            }
            
            logger.info(f"Success: {info.get('title', 'Unknown')[:50]} - {len(formats)} formats")
            return response_data
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"DownloadError: {error_msg}")
        
        # Handle format unavailable error
        if "format is not available" in error_msg.lower():
            # Retry with automatic format selection
            logger.info("Retrying with automatic format selection...")
            return await extract_video(url, format_code=None)
        
        raise HTTPException(status_code=400, detail=f"Download failed: {error_msg[:200]}")
    
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"API Error: {error_msg}")
        
        if "429" in error_msg:
            raise HTTPException(status_code=429, detail="Rate limited. Please try again later.")
        else:
            raise HTTPException(status_code=400, detail=error_msg[:200])

@app.get("/formats")
async def list_formats(url: str = Query(...)):
    """List all available formats for a video without downloading"""
    cookie_path = setup_cookies()
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": cookie_path if cookie_path and os.path.exists(cookie_path) else None,
        "extract_flat": False,
        "listformats": True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get("formats", []):
                if f.get("vcodec") != "none":  # Video formats only
                    formats.append({
                        "format_id": f.get("format_id"),
                        "resolution": f"{f.get('height')}p" if f.get('height') else f.get("format_note"),
                        "ext": f.get("ext"),
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "fps": f.get("fps"),
                        "vcodec": f.get("vcodec"),
                        "acodec": f.get("acodec")
                    })
            
            return {
                "title": info.get("title"),
                "available_formats": formats
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "proxy_count": len(ACTIVE_PROXIES)
    }
