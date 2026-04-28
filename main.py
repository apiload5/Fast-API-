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
from typing import Dict, Any, Optional

app = FastAPI(title="SaveMedia Ultra Final v13.0")
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

# --- Helper Functions ---
def add_force_download_param(url: str) -> str:
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        q['mime'] = ['application/octet-stream']
        return urlunparse(p._replace(query=urlencode(q, doseq=True)))
    except: 
        return url

def sync_extract_info(url: str) -> Dict[str, Any]:
    """Extract video info with multiple fallback strategies"""
    
    # Clean URL (remove any extra parameters)
    if 'youtube.com' in url or 'youtu.be' in url:
        # Extract video ID for cleaner URL
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            clean_url = f'https://www.youtube.com/watch?v={video_id}'
        else:
            clean_url = url
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

    # Try different configurations
    configs = [
        # Config 1: Android client (best success rate)
        {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": temp_cookie_path,
            "socket_timeout": 20,
            "nocheckcertificate": True,
            "format": "best[height<=720]/best",  # Lower resolution for speed
            "noplaylist": True,
            "extract_flat": False,
            "ignoreerrors": False,
            "extractor_args": {
                'youtube': {
                    'player_client': ['android'],
                    'skip': ['hls', 'dash', 'live'],
                }
            },
            "user_agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
        },
        # Config 2: iOS client fallback
        {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": temp_cookie_path,
            "socket_timeout": 20,
            "nocheckcertificate": True,
            "format": "best",
            "noplaylist": True,
            "extract_flat": False,
            "ignoreerrors": True,
            "extractor_args": {
                'youtube': {
                    'player_client': ['ios'],
                }
            },
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        },
        # Config 3: Web client (last resort)
        {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": temp_cookie_path,
            "socket_timeout": 20,
            "nocheckcertificate": True,
            "format": "best[height<=720]/worst",  # Worst case, but better than nothing
            "noplaylist": True,
            "extract_flat": True,  # Flat extraction is faster
            "ignoreerrors": True,
            "extractor_args": {
                'youtube': {
                    'player_client': ['web'],
                }
            },
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
    ]
    
    last_error = None
    
    for idx, config in enumerate(configs):
        try:
            with yt_dlp.YoutubeDL(config) as ydl:
                result = ydl.extract_info(clean_url, download=False)
                
                # Check if we got valid data
                if result and isinstance(result, dict) and result.get("formats"):
                    return result
                elif result and isinstance(result, dict) and result.get("entries"):
                    # Handle playlists (just get first video)
                    if result.get("entries") and len(result["entries"]) > 0:
                        first_entry = result["entries"][0]
                        if first_entry and first_entry.get("formats"):
                            return first_entry
                        
        except Exception as e:
            last_error = str(e)
            continue  # Try next config
    
    # Clean up cookie file
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        try: 
            os.remove(temp_cookie_path)
        except: 
            pass
    
    # If all configs failed
    if last_error:
        error_msg = last_error.split('\n')[0]
        raise Exception(f"Unable to extract video: {error_msg}")
    else:
        raise Exception("Could not extract video information. The video might be private, age-restricted, or unavailable.")

# --- Main API Route ---
@app.get("/download")
async def download_api(url: str = Query(..., description="Video URL")):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, sync_extract_info, url)
        
        # SAFETY CHECK: Ensure info is not None
        if not info:
            raise HTTPException(status_code=400, detail="Could not retrieve video information")
        
        # SAFETY CHECK: Ensure formats exist
        formats = info.get("formats", [])
        if not formats:
            raise HTTPException(status_code=400, detail="No formats available for this video")
        
        formats_data = []
        seen_qualities = set()  # Avoid duplicate qualities
        seen_urls = set()  # Avoid duplicate URLs
        
        for f in formats:
            f_url = f.get("url")
            if not f_url or f_url in seen_urls:
                continue
            
            # Skip problematic formats
            protocol = f.get("protocol", "")
            if protocol in ["m3u8_native", "m3u8"]:
                continue
            
            seen_urls.add(f_url)
            
            # Get format details
            height = f.get('height') or 0
            width = f.get('width') or 0
            fps = f.get('fps') or 0
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            format_id = f.get("format_id", "")
            ext = f.get("ext", "mp4")
            filesize = f.get('filesize') or f.get('filesize_approx')
            tbr = f.get('tbr')  # Total bitrate
            
            # Determine quality label
            if height > 0:
                quality = f"{height}p"
                if width >= 3840:
                    quality = "4K"
                elif width >= 2560:
                    quality = "1440p"
                
                # Add note if 60fps
                if fps >= 60:
                    quality += " (60fps)"
                
                # Add codec info
                if vcodec and 'av01' in vcodec.lower():
                    quality += " [AV1]"
                elif vcodec and 'vp9' in vcodec.lower():
                    quality += " [VP9]"
            else:
                # Audio only or unknown
                if acodec != 'none' and vcodec == 'none':
                    bitrate = f.get('abr', tbr)
                    quality = f"Audio"
                    if bitrate:
                        quality += f" ({int(bitrate)}kbps)"
                else:
                    quality = "SD"
            
            # Create quality key to avoid duplicates
            quality_key = f"{height}_{vcodec}_{acodec}"
            if quality_key in seen_qualities:
                continue
            seen_qualities.add(quality_key)
            
            format_info = {
                "format_id": format_id,
                "ext": ext,
                "resolution": quality,
                "url": f_url,
                "force_download_url": add_force_download_param(f_url),
                "height": height,
                "width": width,
                "filesize": filesize,
                "filesize_mb": round(filesize / (1024 * 1024), 2) if filesize else None,
                "vcodec": vcodec,
                "acodec": acodec
            }
            
            formats_data.append(format_info)

        # Sort by quality (height descending)
        formats_data.sort(key=lambda x: (x['height'], x.get('filesize', 0)), reverse=True)

        # Limit to 10 best formats for performance
        formats_data = formats_data[:10]

        # Get thumbnail safely
        thumbnail = info.get("thumbnail")
        if not thumbnail and info.get("thumbnails"):
            thumbnails = info.get("thumbnails", [])
            if thumbnails:
                thumbnail = thumbnails[-1].get("url")  # Highest quality thumbnail

        return {
            "status": "success",
            "title": info.get("title", "Unknown Title"),
            "thumbnail": thumbnail,
            "uploader": info.get("uploader", "Unknown"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "formats": formats_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        # Clean up error message
        if "HTTP Error 400" in error_detail:
            error_detail = "Video format not available. Try a different video."
        raise HTTPException(status_code=400, detail=error_detail)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "version": "13.0",
        "environment": "verceal"
    }

@app.options("/download")
async def options_download():
    """Handle preflight requests"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
