from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.5")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def setup_cookies():
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w") as f:
                f.write(cookies_data.strip())
            return cookie_path
        except:
            pass
    return None

# Method 1: Try with different configurations
def try_extract_with_config(url, config_name, config):
    try:
        logger.info(f"Trying {config_name}...")
        with yt_dlp.YoutubeDL(config) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get('title'):
                logger.info(f"✅ {config_name} succeeded: {info.get('title')}")
                return info
    except Exception as e:
        logger.warning(f"❌ {config_name} failed: {str(e)[:100]}")
        return None
    return None

@app.get("/download")
async def extract_video(url: str = Query(...)):
    cookie_path = setup_cookies()
    
    # Multiple configuration attempts (try in order)
    configs = [
        {
            "name": "Android Client (Fast)",
            "config": {
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "cookiefile": cookie_path if cookie_path else None,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android"],
                        "player_skip": ["webpage", "configs"],
                    }
                }
            }
        },
        {
            "name": "Web Client",
            "config": {
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "cookiefile": cookie_path if cookie_path else None,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web"],
                        "player_skip": ["webpage"],
                    }
                }
            }
        },
        {
            "name": "Default",
            "config": {
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "cookiefile": cookie_path if cookie_path else None,
            }
        }
    ]
    
    # Try each configuration
    info = None
    for config_item in configs:
        info = try_extract_with_config(url, config_item["name"], config_item["config"])
        if info:
            break
    
    # If all failed, try one more time with minimal config
    if not info:
        logger.info("Trying minimal config...")
        try:
            minimal_config = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,  # Flat extraction first
                "force_generic_extractor": False,
            }
            with yt_dlp.YoutubeDL(minimal_config) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"All attempts failed: {e}")
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot extract video. Check if URL is valid or video is accessible. Error: {str(e)[:150]}"
            )
    
    if not info or not info.get('title'):
        raise HTTPException(
            status_code=400,
            detail="No video information received. Please check the URL and try again."
        )
    
    # Extract video URL
    video_url = None
    
    # Try to get direct URL first
    if info.get('url'):
        video_url = info['url']
    elif info.get('formats'):
        # Find best video URL
        for f in info['formats']:
            if f.get('url') and f.get('vcodec') != 'none':
                video_url = f['url']
                break
        if not video_url and info['formats']:
            video_url = info['formats'][0].get('url')
    
    if not video_url:
        raise HTTPException(
            status_code=400,
            detail="Could not extract video URL. The video might be private or age-restricted."
        )
    
    # Prepare response
    response = {
        "success": True,
        "title": info.get('title', 'Video'),
        "url": video_url,
        "thumbnail": info.get('thumbnail'),
        "duration": info.get('duration'),
        "uploader": info.get('uploader'),
        "video_id": info.get('id'),
        "webpage_url": info.get('webpage_url')
    }
    
    return JSONResponse(content=response)

# Method 2: Simple endpoint for testing
@app.get("/test")
async def test_url(url: str = Query(...)):
    """Simple test endpoint to check if URL works"""
    try:
        # Just check if we can get basic info
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,  # Fast check
            "no_warnings": True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info and info.get('title'):
                return {
                    "status": "success",
                    "title": info.get('title'),
                    "id": info.get('id'),
                    "duration": info.get('duration')
                }
            else:
                return {"status": "failed", "reason": "No data extracted"}
                
    except Exception as e:
        return {"status": "failed", "error": str(e)[:100]}

# Method 3: Alternative using youtube-dl (if yt-dlp fails)
@app.get("/alternative")
async def alternative_extract(url: str = Query(...)):
    """Use youtube-dl as fallback"""
    try:
        import youtube_dl
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = None
            if info.get('url'):
                video_url = info['url']
            elif info.get('formats'):
                for f in info['formats']:
                    if f.get('url') and f.get('vcodec') != 'none':
                        video_url = f['url']
                        break
            
            if video_url:
                return {
                    "success": True,
                    "title": info.get('title'),
                    "url": video_url
                }
            else:
                raise Exception("No video URL found")
                
    except ImportError:
        raise HTTPException(status_code=500, detail="youtube-dl not installed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:150])

# Method 4: Direct ID extraction
@app.get("/from-id")
async def extract_from_id(video_id: str = Query(...)):
    """Extract using just video ID"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    return await extract_video(url)

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "API is working",
        "endpoints": ["/download", "/test", "/alternative", "/from-id"]
    }
