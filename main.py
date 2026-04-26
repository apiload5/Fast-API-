from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
import random
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API with Fresh Proxy", version="3.6")

# CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global proxy cache with TTL
last_proxy = None
last_proxy_time = None
PROXY_TTL = 3  # 3 seconds

async def get_fresh_proxy() -> Optional[str]:
    """Har request ke liye fresh proxy 4 seconds mein"""
    global last_proxy, last_proxy_time
    
    # Check if existing proxy is still fresh (less than 3 seconds old)
    if last_proxy and last_proxy_time:
        age = (datetime.now() - last_proxy_time).total_seconds()
        if age < PROXY_TTL:
            return last_proxy
    
    # Fetch new proxy (free and fast)
    proxy_urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=2000&ssl=all"
    ]
    
    try:
        async with aiohttp.ClientSession() as session:
            for api_url in proxy_urls:
                try:
                    # 3 seconds timeout for fetching
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            proxies = parse_proxy_list(text)
                            
                            if proxies:
                                # Test first working proxy
                                for proxy in proxies[:5]:  # Try first 5
                                    if await test_proxy_speed(session, proxy):
                                        last_proxy = proxy
                                        last_proxy_time = datetime.now()
                                        logger.info(f"Fresh proxy obtained: {proxy}")
                                        return proxy
                except Exception as e:
                    logger.warning(f"Proxy source failed: {str(e)[:50]}")
                    continue
    except Exception as e:
        logger.error(f"Proxy fetch error: {e}")
    
    return None

def parse_proxy_list(text: str) -> list:
    """Parse proxy list from text"""
    proxies = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            parts = line.split(':')
            if len(parts) >= 2:
                proxy_url = f"http://{parts[0]}:{parts[1]}"
                proxies.append(proxy_url)
    return proxies

async def test_proxy_speed(session: aiohttp.ClientSession, proxy: str) -> bool:
    """Test proxy speed (must be under 2 seconds)"""
    try:
        start = datetime.now()
        async with session.get(
            "https://httpbin.org/ip",
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=2)
        ) as resp:
            if resp.status == 200:
                elapsed = (datetime.now() - start).total_seconds()
                return elapsed < 2.0
    except:
        pass
    return False

@app.get("/")
async def root():
    return {
        "status": "active",
        "message": "SaveMedia API with Fresh Proxy",
        "proxy_fresh_interval": f"{PROXY_TTL} seconds"
    }

@app.get("/download")
async def extract_video(url: str = Query(...)):
    """Extract video with fresh proxy each time"""
    import time
    start_time = time.time()
    
    # Step 1: Get fresh proxy (under 4 seconds)
    proxy_start = time.time()
    proxy_url = await get_fresh_proxy()
    proxy_time = (time.time() - proxy_start) * 1000
    
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except: 
            pass

    try:
        # Step 2: yt-dlp options with fresh proxy
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "com.google.android.youtube/19.12.35 (Linux; Android 14) gzip"
            ]),
            "format": "best[ext=mp4]/best",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "proxy": proxy_url if proxy_url else None,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios"],
                    "player_skip": ["webpage", "configs"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = info.get("formats", [info])
            processed = []

            for f in formats:
                f_url = f.get("url")
                if not f_url: 
                    continue

                is_youtube = "youtube" in url or "youtu.be" in url
                has_both = f.get("vcodec") != "none" and f.get("acodec") != "none"

                if (is_youtube and has_both) or (not is_youtube and f.get("vcodec") != "none"):
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "HD")

                    processed.append({
                        "resolution": res,
                        "ext": f.get("ext", "mp4"),
                        "url": f_url,
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "format_note": f.get("format_note") or "Standard"
                    })

            # Remove duplicates
            unique_list = {}
            for item in processed:
                if item['resolution'] not in unique_list:
                    unique_list[item['resolution']] = item
            
            final_formats = sorted(unique_list.values(), key=lambda x: str(x['resolution']), reverse=True)

            total_time = (time.time() - start_time) * 1000
            
            return {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": final_formats[:5],  # Limit to 5 formats for speed
                "proxy_used": bool(proxy_url),
                "proxy_fetch_time_ms": round(proxy_time, 2),
                "total_time_ms": round(total_time, 2),
                "proxy_fresh": True
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"Error: {error_msg}")
        
        # Retry without proxy if proxy failed
        if "proxy" in error_msg.lower() or "connection" in error_msg.lower():
            try:
                logger.info("Retrying without proxy...")
                ydl_opts_no_proxy = {
                    "quiet": True,
                    "no_warnings": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "format": "best[ext=mp4]/best",
                }
                with yt_dlp.YoutubeDL(ydl_opts_no_proxy) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return {
                        "title": info.get("title", "Video"),
                        "using_proxy": False,
                        "fallback": True
                    }
            except Exception as e2:
                raise HTTPException(status_code=400, detail=str(e2))
        
        raise HTTPException(status_code=400, detail=error_msg)

@app.get("/proxy-status")
async def check_proxy():
    """Quick proxy status check"""
    start = time.time()
    proxy = await get_fresh_proxy()
    elapsed = (time.time() - start) * 1000
    
    return {
        "proxy_available": bool(proxy),
        "fetch_time_ms": round(elapsed, 2),
        "under_4_seconds": elapsed < 4000,
        "proxy_url": proxy if proxy else None
    }
