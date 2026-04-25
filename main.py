from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.4")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Temporarily allow all for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=2)

def setup_cookies():
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
            return cookie_path
        except:
            pass
    return None

# FAST yt-dlp options - MINIMAL configuration
def get_fast_ydl_opts(cookie_path=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,  # KEY: Only get basic info, NO formats
        "playlistend": 1,       # Only first video
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "no_color": True,
    }
    
    if cookie_path and os.path.exists(cookie_path):
        opts["cookiefile"] = cookie_path
    
    # Add Android client for faster response
    opts["extractor_args"] = {
        "youtube": {
            "player_client": ["android"],  # Fastest client
            "skip": ["hls", "dash"],       # Skip heavy formats
        }
    }
    
    return opts

@app.get("/download")
async def extract_video(url: str = Query(...)):
    start_time = time.time()
    cookie_path = setup_cookies()
    
    try:
        # Use thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def extract_info():
            ydl_opts = get_fast_ydl_opts(cookie_path)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract ONLY basic info (super fast)
                info = ydl.extract_info(url, download=False)
                return info
        
        # Set timeout for the operation
        info = await asyncio.wait_for(
            loop.run_in_executor(executor, extract_info),
            timeout=10.0  # 10 seconds max
        )
        
        if not info:
            raise Exception("No data received")
        
        # Get just the essential information
        video_url = info.get("url")
        
        # If no direct URL, try to get from formats (but limit)
        if not video_url and info.get("formats"):
            # Take only first few formats (fast)
            for f in info.get("formats", [])[:3]:
                if f.get("height") and f.get("url"):
                    video_url = f.get("url")
                    break
            if not video_url and info.get("formats"):
                video_url = info["formats"][0].get("url")
        
        # Simple response with essential data
        response = {
            "success": True,
            "title": info.get("title", "Video"),
            "url": video_url,
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "response_time": round(time.time() - start_time, 2)
        }
        
        logger.info(f"Response time: {response['response_time']}s for {url[:50]}")
        return JSONResponse(content=response)
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout after {time.time() - start_time}s for {url}")
        raise HTTPException(
            status_code=504, 
            detail="Request timeout. Video processing took too long."
        )
    except Exception as e:
        error_msg = str(e)[:150]
        logger.error(f"Error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

# ============ EVEN FASTER: Direct URL extraction ============
@app.get("/direct")
async def get_direct_url(url: str = Query(...)):
    """Super fast - just get direct video URL without any processing"""
    
    # Manual extraction for common YouTube patterns
    try:
        # Fastest method: Use youtube-dl with minimal options
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "geturl": True,  # Just get URL
            "no_warnings": True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get the best available stream URL
            video_url = info.get("url")
            if not video_url and info.get("formats"):
                # Get highest quality available
                for f in sorted(info.get("formats", []), 
                               key=lambda x: x.get("height", 0), 
                               reverse=True):
                    if f.get("url"):
                        video_url = f.get("url")
                        break
            
            if video_url:
                return {
                    "success": True,
                    "url": video_url,
                    "title": info.get("title", "Video")
                }
            else:
                raise Exception("No video URL found")
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])

# ============ CACHED RESPONSES ============
from functools import lru_cache
from datetime import datetime, timedelta

# Simple in-memory cache
cache = {}
cache_timeout = 300  # 5 minutes

@app.get("/cached")
async def get_cached_video(url: str = Query(...)):
    """Cached version - even faster for repeated requests"""
    
    current_time = datetime.now()
    
    # Check cache
    if url in cache:
        cached_data, cached_time = cache[url]
        if (current_time - cached_time).seconds < cache_timeout:
            logger.info(f"Cache hit for {url[:50]}")
            return cached_data
    
    # Get fresh data
    try:
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "no_warnings": True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = info.get("url")
            if not video_url and info.get("formats"):
                for f in info.get("formats", []):
                    if f.get("height") and f.get("url"):
                        video_url = f.get("url")
                        break
            
            response = {
                "success": True,
                "title": info.get("title"),
                "url": video_url,
                "thumbnail": info.get("thumbnail")
            }
            
            # Store in cache
            cache[url] = (response, current_time)
            
            return response
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])

# ============ HEALTH CHECK ============
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "cache_size": len(cache),
        "thread_pool": executor._max_workers
    }
