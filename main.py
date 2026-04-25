from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import os
import logging
from typing import Optional
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.7")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_cookies_from_browser(browser_name: str = "chrome"):
    """
    Extract cookies from browser using browser_cookie3
    Supported browsers: chrome, firefox, opera, edge, chromium, brave
    """
    try:
        import browser_cookie3
        
        # Map browser names to functions
        browsers = {
            "chrome": browser_cookie3.chrome,
            "firefox": browser_cookie3.firefox,
            "opera": browser_cookie3.opera,
            "edge": browser_cookie3.edge,
            "chromium": browser_cookie3.chromium,
            "brave": browser_cookie3.brave
        }
        
        if browser_name.lower() not in browsers:
            logger.warning(f"Browser {browser_name} not supported. Using chrome.")
            browser_name = "chrome"
        
        # Get cookies for youtube.com
        logger.info(f"Fetching cookies from {browser_name}...")
        cj = browsers[browser_name](domain_name='youtube.com')
        
        # Create temporary cookie file in Netscape format
        cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        
        # Write cookies in Netscape format
        cookie_file.write("# Netscape HTTP Cookie File\n")
        
        cookie_count = 0
        for cookie in cj:
            if 'youtube.com' in cookie.domain or '.youtube.com' in cookie.domain:
                # Format: domain\tflag\tpath\tsecure\texpires\tname\tvalue
                domain = cookie.domain
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = cookie.path
                secure = 'TRUE' if cookie.secure else 'FALSE'
                expires = int(cookie.expires) if cookie.expires else 0
                name = cookie.name
                value = cookie.value
                
                cookie_file.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                cookie_count += 1
        
        cookie_file.close()
        
        if cookie_count == 0:
            logger.warning("No YouTube cookies found!")
            return None
            
        logger.info(f"✅ Extracted {cookie_count} cookies from {browser_name}")
        return cookie_file.name
        
    except ImportError:
        logger.error("browser_cookie3 not installed. Install with: pip install browser-cookie3")
        return None
    except Exception as e:
        logger.error(f"Failed to get cookies from browser: {e}")
        return None

def get_cookies_from_env():
    """Get cookies from environment variable"""
    cookies_content = os.getenv("YOUTUBE_COOKIES")
    if cookies_content:
        try:
            cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
            cookie_file.write(cookies_content)
            cookie_file.close()
            logger.info("✅ Loaded cookies from environment variable")
            return cookie_file.name
        except Exception as e:
            logger.error(f"Failed to load cookies from env: {e}")
    return None

def get_cookies_from_file():
    """Get cookies from file path"""
    cookie_paths = [
        "/app/cookies.txt",
        "./cookies.txt",
        "/tmp/cookies.txt",
        os.getenv("COOKIE_FILE_PATH", "")
    ]
    
    for path in cookie_paths:
        if path and os.path.exists(path):
            logger.info(f"✅ Found cookies file: {path}")
            return path
    
    return None

@app.get("/download")
async def extract_video(
    url: str = Query(...),
    browser: Optional[str] = Query("chrome", description="Browser to extract cookies from (chrome, firefox, edge, etc)"),
    use_browser_cookies: Optional[bool] = Query(True, description="Use browser cookies if available"),
    format_quality: Optional[str] = Query("best", description="Video quality (best, 1080p, 720p, 480p, 360p)")
):
    """
    Download video using cookies from browser
    """
    cookie_file = None
    
    # Method 1: Try browser cookies (if enabled)
    if use_browser_cookies:
        cookie_file = get_cookies_from_browser(browser)
    
    # Method 2: Try environment variable
    if not cookie_file:
        cookie_file = get_cookies_from_env()
    
    # Method 3: Try cookie file
    if not cookie_file:
        cookie_file = get_cookies_from_file()
    
    if not cookie_file:
        logger.warning("No cookies found. Trying without cookies...")
    
    # Set format based on quality
    format_map = {
        "best": "best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
        "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]"
    }
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "format": format_map.get(format_quality, "best[ext=mp4]/best"),
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage", "configs"],
            }
        },
        "http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        }
    }
    
    # Add cookie file if available
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file
        logger.info(f"Using cookies from: {cookie_file}")
    
    try:
        logger.info(f"Extracting video: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract video info
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="No video information received")
            
            # Get video URL
            video_url = None
            video_formats = []
            
            # Process formats
            if info.get('formats'):
                for f in info['formats']:
                    if f.get('vcodec') != 'none':  # Video formats only
                        format_data = {
                            "format_id": f.get('format_id'),
                            "resolution": f"{f.get('height')}p" if f.get('height') else f.get('format_note', 'Unknown'),
                            "ext": f.get('ext'),
                            "filesize": f.get('filesize') or f.get('filesize_approx'),
                            "fps": f.get('fps'),
                            "has_audio": f.get('acodec') != 'none'
                        }
                        video_formats.append(format_data)
                        
                        # Select best URL based on quality preference
                        if not video_url:
                            if format_quality == "best":
                                if f.get('height') and f.get('height') >= 720:
                                    video_url = f.get('url')
                            elif format_quality == "1080p" and f.get('height') == 1080:
                                video_url = f.get('url')
                            elif format_quality == "720p" and f.get('height') == 720:
                                video_url = f.get('url')
                            elif format_quality == "480p" and f.get('height') == 480:
                                video_url = f.get('url')
                            elif format_quality == "360p" and f.get('height') == 360:
                                video_url = f.get('url')
            
            # Fallback to direct URL
            if not video_url and info.get('url'):
                video_url = info['url']
            
            # Last resort: get any video URL
            if not video_url and video_formats:
                for f in info['formats']:
                    if f.get('url') and f.get('vcodec') != 'none':
                        video_url = f.get('url')
                        break
            
            if not video_url:
                raise HTTPException(status_code=400, detail="Could not extract video URL")
            
            # Prepare response
            response = {
                "success": True,
                "title": info.get('title', 'Video'),
                "url": video_url,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "video_id": info.get('id'),
                "view_count": info.get('view_count'),
                "like_count": info.get('like_count'),
                "formats_available": len(video_formats),
                "all_formats": video_formats[:10],  # Send first 10 formats
                "cookies_used": cookie_file is not None,
                "browser_used": browser if cookie_file else None
            }
            
            logger.info(f"✅ Success: {info.get('title', 'Unknown')[:50]} - Cookies: {cookie_file is not None}")
            
            # Cleanup temp cookie file
            if cookie_file and cookie_file.startswith('/tmp/'):
                try:
                    os.unlink(cookie_file)
                except:
                    pass
            
            return JSONResponse(content=response)
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error: {error_msg}")
        
        # Cleanup temp file on error
        if cookie_file and cookie_file.startswith('/tmp/'):
            try:
                os.unlink(cookie_file)
            except:
                pass
        
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(
                status_code=403,
                detail="YouTube bot detection triggered. Please ensure you're logged into YouTube in your browser."
            )
        elif "Private video" in error_msg:
            raise HTTPException(status_code=403, detail="This video is private")
        elif "age" in error_msg.lower():
            raise HTTPException(status_code=403, detail="This video is age-restricted")
        else:
            raise HTTPException(status_code=400, detail=error_msg[:300])

@app.get("/browsers")
async def list_browsers():
    """List available browsers for cookie extraction"""
    try:
        import browser_cookie3
        available = []
        
        browsers = {
            "chrome": browser_cookie3.chrome,
            "firefox": browser_cookie3.firefox,
            "edge": browser_cookie3.edge,
            "opera": browser_cookie3.opera,
            "brave": browser_cookie3.brave,
            "chromium": browser_cookie3.chromium
        }
        
        for name, func in browsers.items():
            try:
                cookies = func(domain_name='youtube.com')
                count = sum(1 for _ in cookies)
                if count > 0:
                    available.append(f"{name} ({count} cookies)")
                else:
                    available.append(f"{name} (no YouTube cookies)")
            except:
                available.append(f"{name} (not available)")
        
        return {
            "available_browsers": available,
            "tip": "Make sure you're logged into YouTube in your browser"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/test-browser")
async def test_browser_cookies(browser: str = Query("chrome")):
    """Test if browser cookies are working"""
    cookie_file = get_cookies_from_browser(browser)
    
    if not cookie_file:
        return {
            "success": False,
            "message": f"No cookies found in {browser}. Make sure you're logged into YouTube."
        }
    
    # Test with a simple video
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Public video
    
    ydl_opts = {
        "quiet": True,
        "cookiefile": cookie_file,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            
            # Cleanup
            os.unlink(cookie_file)
            
            return {
                "success": True,
                "message": f"✅ Cookies working! Found {info.get('title')}",
                "browser": browser
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Cookies found but failed: {str(e)[:100]}"
        }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "3.7",
        "endpoints": [
            "/download?url=VIDEO_URL&browser=chrome&format_quality=720p",
            "/browsers",
            "/test-browser?browser=chrome",
            "/health"
        ],
        "notes": "Make sure you're logged into YouTube in your browser"
    }
