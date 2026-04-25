from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
from typing import Optional
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.8")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cookie file path
COOKIE_FILE_PATH = "/tmp/youtube_cookies.txt"

def setup_cookies():
    """
    Setup cookies from environment variable or file
    This works on servers where browser_cookie3 is not available
    """
    # Priority 1: Check environment variable
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    if cookies_content:
        try:
            with open(COOKIE_FILE_PATH, "w") as f:
                f.write(cookies_content)
            logger.info("✅ Cookies loaded from environment variable")
            return COOKIE_FILE_PATH
        except Exception as e:
            logger.error(f"Failed to write cookies from env: {e}")
    
    # Priority 2: Check if cookies file exists
    if os.path.exists("/app/cookies.txt"):
        logger.info("✅ Using cookies from /app/cookies.txt")
        return "/app/cookies.txt"
    
    if os.path.exists("cookies.txt"):
        logger.info("✅ Using cookies from ./cookies.txt")
        return "cookies.txt"
    
    # No cookies found
    logger.warning("⚠️ No cookies found! Will try without cookies.")
    return None

@app.get("/download")
async def extract_video(
    url: str = Query(...),
    quality: Optional[str] = Query("720p", description="Video quality: 1080p, 720p, 480p, 360p, best")
):
    """
    Download video using cookies from environment variable
    """
    cookie_file = setup_cookies()
    
    # Quality presets
    quality_formats = {
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
        "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]",
        "best": "best[ext=mp4]/best"
    }
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "format": quality_formats.get(quality, quality_formats["720p"]),
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage", "configs"],
            }
        }
    }
    
    # Add cookies if available
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file
        logger.info(f"✅ Using cookies from: {cookie_file}")
    else:
        logger.warning("⚠️ No cookies available - may get bot detection error")
    
    try:
        logger.info(f"Extracting video: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="No video information received")
            
            # Get video URL
            video_url = None
            
            # Try to get best format URL
            if info.get('url'):
                video_url = info['url']
            elif info.get('formats'):
                # Find format matching requested quality
                target_height = int(quality.replace('p', '')) if quality != 'best' else 1080
                
                for f in info['formats']:
                    if f.get('vcodec') != 'none':
                        height = f.get('height', 0)
                        if quality == 'best' or height == target_height:
                            if f.get('acodec') != 'none':  # Prefer formats with audio
                                video_url = f.get('url')
                                break
                
                # If no exact match, get highest quality
                if not video_url:
                    for f in sorted(info['formats'], key=lambda x: x.get('height', 0), reverse=True):
                        if f.get('vcodec') != 'none' and f.get('url'):
                            video_url = f.get('url')
                            break
            
            if not video_url:
                raise HTTPException(status_code=400, detail="Could not extract video URL")
            
            response = {
                "success": True,
                "title": info.get('title', 'Video'),
                "url": video_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "video_id": info.get('id'),
                "quality": quality,
                "cookies_used": cookie_file is not None
            }
            
            logger.info(f"✅ Success: {info.get('title', 'Unknown')[:50]}")
            return JSONResponse(content=response)
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error: {error_msg}")
        
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(
                status_code=403,
                detail="YouTube bot detection triggered. Please set YOUTUBE_COOKIES environment variable with valid cookies."
            )
        else:
            raise HTTPException(status_code=400, detail=error_msg[:300])

@app.post("/set-cookies")
async def set_cookies(cookies: str = Query(...)):
    """Set cookies via API (for testing)"""
    try:
        with open(COOKIE_FILE_PATH, "w") as f:
            f.write(cookies)
        return {"success": True, "message": "Cookies saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
