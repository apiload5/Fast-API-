from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(
    title="SaveMedia Backend",
    version="2.1"
)

# --- Restricted CORS (As per your request) ---
allowed_origins = [
    "https://savemedia.online",
    "https://www.savemedia.online",
    "https://ticnotester.blogspot.com",
    "http://localhost:3000" # Testing ke liye
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "online", "message": "SaveMedia API is running"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL")):
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    # 1. Cookies Writing with Error Handling
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except Exception as e:
            logger.error(f"Cookie Write Error: {e}")

    try:
        logger.info(f"Extracting URL: {url}")

        # 2. Optimized YT-DLP Options
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "format": "best[ext=mp4]/best",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web", "ios"],
                    "player_skip": ["webpage", "configs"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_title = info.get("title", "Video")
            thumbnail = info.get("thumbnail")
            duration = info.get("duration")
            uploader = info.get("uploader")
            
            # 3. Format Processing
            formats = info.get("formats", [])
            processed_formats = []

            for f in formats:
                f_url = f.get("url")
                if not f_url: continue

                # Platform base filtering
                is_video = f.get("vcodec") != "none" or "fbcdn" in f_url or "tiktok" in f_url
                
                if is_video:
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "HD")
                    
                    # Force Download Logic
                    try:
                        p = urlparse(f_url)
                        qs = parse_qs(p.query)
                        qs['mime'] = ['application/octet-stream']
                        force_url = urlunparse(p._replace(query=urlencode(qs, doseq=True)))
                    except:
                        force_url = f_url

                    processed_formats.append({
                        "resolution": res,
                        "ext": f.get("ext", "mp4"),
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "url": f_url,
                        "force_download_url": force_url,
                        "format_note": f.get("format_note", "Standard")
                    })

            # Duplicate resolutions saaf karna
            unique_formats = {res['resolution']: res for res in processed_formats}.values()
            final_list = sorted(unique_formats, key=lambda x: str(x['resolution']), reverse=True)

            if not final_list:
                raise Exception("YouTube hidden formats. Please check cookies.")

            return {
                "title": video_title,
                "thumbnail": thumbnail,
                "duration": duration,
                "uploader": uploader,
                "formats": list(final_list)
            }

    except Exception as e:
        # Ye line asli error dikhayegi ke kiyon fail hua
        error_detail = str(e) 
        logger.error(f"Full Error: {error_detail}")
        raise HTTPException(status_code=400, detail=error_detail)
