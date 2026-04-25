from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
import random
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from proxy_manager import proxy_manager
import asyncio
from cachetools import TTLCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API with Fresh Proxy", version="3.6")

# Cache for proxy (but only for 3 seconds)
proxy_cache = TTLCache(maxsize=1, ttl=3)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_proxy_under_4_seconds() -> str:
    """3.5 seconds mein fresh proxy deliver karega"""
    
    # Check cache (but cache is only 3 seconds old)
    if "proxy" in proxy_cache:
        return proxy_cache["proxy"]
    
    # Get fresh proxy with timeout
    try:
        proxy_task = proxy_manager.get_fresh_proxy()
        proxy = await asyncio.wait_for(proxy_task, timeout=3.5)
        
        if proxy:
            proxy_cache["proxy"] = proxy
            logger.info(f"Fresh proxy obtained: {proxy}")
            return proxy
    except asyncio.TimeoutError:
        logger.warning("Proxy fetch timeout, using fallback")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
    
    return None

@app.get("/download")
async def extract_video(url: str = Query(...), background_tasks: BackgroundTasks = None):
    """Main endpoint with fresh proxy each time"""
    
    # Step 1: Get fresh proxy (under 4 seconds)
    start_time = asyncio.get_event_loop().time()
    proxy_url = await get_proxy_under_4_seconds()
    proxy_time = asyncio.get_event_loop().time() - start_time
    
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
                "com.google.android.youtube/19.12.35 (Linux; U; Android 14; en_US; Pixel 7 Pro) gzip",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ]),
            
            "format": "best[ext=mp4]/best",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            
            # Fresh proxy
            "proxy": proxy_url if proxy_url else None,
            
            # Rotate IP addresses
            "source_address": random.choice(["::", "0.0.0.0"]),
            
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "tvhtml5", "web_music"],
                    "player_skip": ["webpage", "configs"],
                    "skip": ["hls", "dash"]
                }
            },
            
            # Speed optimizations
            "extract_flat": False,
            "force_generic_extractor": False,
        }

        # Step 3: Extract video info (should be fast due to fresh proxy)
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
                    
                    try:
                        p = urlparse(f_url)
                        q = parse_qs(p.query)
                        q['mime'] = ['application/octet-stream']
                        force_url = urlunparse(p._replace(query=urlencode(q, doseq=True)))
                    except:
                        force_url = f_url

                    processed.append({
                        "resolution": res,
                        "ext": f.get("ext", "mp4"),
                        "url": f_url,
                        "force_download_url": force_url,
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "format_note": f.get("format_note") or "Standard"
                    })

            unique_list = {res['resolution']: res for res in processed}.values()
            final_formats = sorted(unique_list, key=lambda x: str(x['resolution']), reverse=True)

            total_time = (asyncio.get_event_loop().time() - start_time) * 1000  # ms
            
            return {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(final_formats),
                "using_proxy": bool(proxy_url),
                "proxy_url": proxy_url if proxy_url else "none",
                "proxy_fetch_time_ms": round(proxy_time * 1000, 2),
                "total_time_ms": round(total_time, 2),
                "proxy_fresh": True
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"API Error: {error_msg}")
        
        # Retry without proxy if proxy failed
        if "proxy" in error_msg.lower() or "connection" in error_msg.lower():
            try:
                logger.info("Retrying without proxy...")
                ydl_opts_no_proxy = {
                    "quiet": True,
                    "no_warnings": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "format": "best[ext=mp4]/best",
                    "geo_bypass": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts_no_proxy) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return {
                        "title": info.get("title", "Video"),
                        "using_proxy": False,
                        "fallback": True
                    }
            except:
                pass
        
        raise HTTPException(status_code=400, detail=error_msg)

@app.get("/proxy-status")
async def proxy_status():
    """Check proxy performance"""
    start = asyncio.get_event_loop().time()
    proxy = await get_proxy_under_4_seconds()
    elapsed = (asyncio.get_event_loop().time() - start) * 1000
    
    return {
        "proxy_working": bool(proxy),
        "fetch_time_ms": round(elapsed, 2),
        "under_4_seconds": elapsed < 4000
    }
