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

app = FastAPI(title="SaveMedia API", version="3.2")

# Restricted CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ PROXY CONFIGURATION ============
# Method 1: Static proxy list (manually update)
PROXY_LIST = [
    # Add your working proxies here
    # "http://username:password@ip:port",
    # "socks5://username:password@ip:port",
]

# Method 2: Fetch fresh proxies from API
def fetch_fresh_proxies():
    """Get working proxies from free proxy APIs"""
    proxies = []
    try:
        # Free proxy APIs (you can add more)
        proxy_apis = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTP_RAW.txt",
        ]
        
        for api in proxy_apis:
            try:
                response = requests.get(api, timeout=10)
                if response.status_code == 200:
                    raw_proxies = response.text.strip().split('\n')
                    for proxy in raw_proxies[:20]:  # Limit to 20 proxies
                        proxy = proxy.strip()
                        if proxy and ':' in proxy:
                            if not proxy.startswith('http'):
                                proxy = f"http://{proxy}"
                            proxies.append(proxy)
            except:
                continue
        
        # Remove duplicates
        proxies = list(set(proxies))
        logger.info(f"Fetched {len(proxies)} proxies")
        return proxies
    except Exception as e:
        logger.error(f"Proxy fetch failed: {e}")
        return []

# Method 3: Environment variable for proxy list
ENV_PROXIES = os.getenv("PROXY_LIST", "")
if ENV_PROXIES:
    PROXY_LIST.extend([p.strip() for p in ENV_PROXIES.split(',') if p.strip()])

# Global proxy list with fallback
ACTIVE_PROXIES = PROXY_LIST + fetch_fresh_proxies()
FAILED_PROXIES = set()

def get_working_proxy(max_attempts=3):
    """Get a working proxy with retry mechanism"""
    available_proxies = [p for p in ACTIVE_PROXIES if p not in FAILED_PROXIES]
    
    if not available_proxies:
        logger.warning("No proxies available, using direct connection")
        return None
    
    # Try random proxies up to max_attempts
    for attempt in range(min(max_attempts, len(available_proxies))):
        proxy = random.choice(available_proxies)
        
        # Test proxy quickly
        try:
            test_response = requests.get(
                "https://www.youtube.com", 
                proxies={"http": proxy, "https": proxy},
                timeout=5
            )
            if test_response.status_code == 200:
                logger.info(f"Proxy working: {proxy}")
                return proxy
            else:
                FAILED_PROXIES.add(proxy)
                logger.warning(f"Proxy failed test: {proxy}")
        except Exception as e:
            FAILED_PROXIES.add(proxy)
            logger.warning(f"Proxy error: {proxy} - {str(e)[:50]}")
            continue
    
    logger.warning("No working proxies found")
    return None

# ============ COOKIE MANAGEMENT ============
def setup_cookies():
    """Setup cookie file from environment variable"""
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
            logger.info("Cookies configured successfully")
            return cookie_path
        except Exception as e:
            logger.error(f"Cookie setup failed: {e}")
    return None

# ============ MAIN DOWNLOAD FUNCTION ============
@app.get("/download")
async def extract_video(
    url: str = Query(...), 
    use_proxy: Optional[bool] = Query(True),
    force_format: Optional[str] = Query(None)
):
    cookie_path = setup_cookies()
    
    # Get working proxy if enabled
    proxy_url = None
    if use_proxy:
        proxy_url = get_working_proxy()
        if proxy_url:
            logger.info(f"Using proxy: {proxy_url}")
    
    ydl_opts = {
        "quiet": True,
        "no_whitelist": True,
        "no_warnings": True,
        "cookiefile": cookie_path if cookie_path and os.path.exists(cookie_path) else None,
        "user_agent": random.choice([  # Random user agents
            "com.google.android.youtube/19.12.35 (Linux; U; Android 14; en_US; Pixel 7 Pro) gzip",
            "com.google.android.youtube/18.45.43 (Linux; U; Android 13; en_US; SM-G998B) gzip",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ]),
        "format": force_format or "best[ext=mp4]/best",
        "nocheckcertificate": True,
        "geo_bypass": True,
        "source_address": random.choice(["::", "0.0.0.0"]),  # Random IP version
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "tvhtml5", "web"],
                "player_skip": ["webpage", "configs"],
            }
        }
    }
    
    # Add proxy if available
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting info for URL: {url}")
            info = ydl.extract_info(url, download=False)
            
            formats = info.get("formats", [info])
            processed = []
            
            for f in formats:
                f_url = f.get("url")
                if not f_url:
                    continue
                
                is_youtube = "youtube.com" in url or "youtu.be" in url
                has_both = f.get("vcodec") != "none" and f.get("acodec") != "none"
                
                if (is_youtube and has_both) or (not is_youtube and f.get("vcodec") != "none"):
                    # Format resolution
                    height = f.get("height")
                    if height:
                        res = f"{height}p"
                    else:
                        res = f.get("resolution") or f.get("format_note") or "HD"
                    
                    # Create force download URL
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
                        "format_note": f.get("format_note") or "Standard",
                        "fps": f.get("fps"),
                        "vcodec": f.get("vcodec"),
                        "acodec": f.get("acodec")
                    })
            
            # Remove duplicates and sort
            unique_list = {res['resolution']: res for res in processed}.values()
            final_formats = sorted(unique_list, key=lambda x: int(x['resolution'].replace('p', '')) if x['resolution'].replace('p', '').isdigit() else 0, reverse=True)
            
            response_data = {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(final_formats),
                "proxy_used": bool(proxy_url),
                "success": True
            }
            
            logger.info(f"Successfully extracted {len(final_formats)} formats for: {info.get('title', 'Unknown')[:50]}")
            return response_data
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"DownloadError: {error_msg}")
        
        # Retry without proxy if proxy was used
        if proxy_url and "429" in error_msg or "unavailable" in error_msg.lower():
            logger.info("Retrying without proxy...")
            return await extract_video(url, use_proxy=False, force_format=force_format)
        
        raise HTTPException(status_code=400, detail=f"Download failed: {error_msg[:200]}")
    
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"API Error: {error_msg}")
        
        # Provide helpful error messages
        if "429" in error_msg:
            raise HTTPException(status_code=429, detail="Rate limited. Please try again later.")
        elif "unavailable" in error_msg.lower():
            raise HTTPException(status_code=503, detail="Service temporarily unavailable. Retry in a moment.")
        else:
            raise HTTPException(status_code=400, detail=error_msg[:200])

# ============ HEALTH CHECK ENDPOINT ============
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "proxy_count": len([p for p in ACTIVE_PROXIES if p not in FAILED_PROXIES]),
        "total_proxies": len(ACTIVE_PROXIES),
        "failed_proxies": len(FAILED_PROXIES)
    }
