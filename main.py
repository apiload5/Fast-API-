from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# Logging setup for Vercel dashboard
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia Ultimate API", version="4.1")

# Restricted CORS for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://savemedia.online", "https://www.savemedia.online", "https://ticnotester.blogspot.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/download")
async def extract_video(url: str = Query(...)):
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    proxy_url = os.getenv("PROXY_URL")
    
    # Setup Cookies from Environment Variable
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except Exception as e:
            logger.error(f"Cookie setup failed: {e}")

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            
            # Powerful Android User-Agent to mimic real app traffic
            "user_agent": "com.google.android.youtube/19.12.35 (Linux; U; Android 14; en_US; Pixel 7 Pro) gzip",
            
            # Format: prioritizing merged MP4 for Vercel compatibility (no FFmpeg needed)
            "format": "best[vcodec!=none][acodec!=none][ext=mp4]/best",
            
            "nocheckcertificate": True,
            "geo_bypass": True,
            
            # ✅ Fixed Network Config
            "proxy": proxy_url if proxy_url else None,
            # source_address removed to fix DNS resolution error (-9)
            
            # ✅ Plugin & Token support (if yt-dlp-get-pot is in requirements.txt)
            "plugin_dirs": ["/tmp/yt-dlp-plugins"], 
            
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "tvhtml5"],
                    "player_skip": ["webpage", "configs"],
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Data Extraction
            info = ydl.extract_info(url, download=False)
            
            formats = info.get("formats", [info])
            processed = []

            for f in formats:
                f_url = f.get("url")
                if not f_url: continue

                is_youtube = "youtube" in url or "youtu.be" in url
                has_both = f.get("vcodec") != "none" and f.get("acodec") != "none"

                # Filter for merged formats for YouTube, any video for others
                if (is_youtube and has_both) or (not is_youtube and f.get("vcodec") != "none"):
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "HD")
                    
                    # Force Download link logic (injecting octet-stream)
                    try:
                        p = urlparse(f_url); q = parse_qs(p.query)
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

            # Duplicate cleaning & Sorting by resolution
            unique_list = {res['resolution']: res for res in processed}.values()
            final_formats = sorted(unique_list, key=lambda x: str(x['resolution']), reverse=True)

            return {
                "success": True,
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(final_formats),
                "debug": {
                    "proxy_active": bool(proxy_url),
                    "server_region": "iad1"
                }
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"Critical API Error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
