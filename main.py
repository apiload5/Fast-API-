from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# --- Logging Setup (Vercel Logs ke liye) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(
    title="SaveMedia Backend",
    version="1.9",
    description="Universal Downloader - YouTube, FB, TikTok Support"
)

# --- CORS: Sirf savemedia.online aur allowed domains ---
allowed_origins = [
    "https://savemedia.online",
    "https://www.savemedia.online",
    "https://ticnotester.blogspot.com"
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
    return {"message": "✅ SaveMedia Backend is Fully Operational!"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL to extract")):
    # 1. Cookies Handling (From Environment Variable)
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
            logger.info("Cookies loaded into /tmp/cookies.txt")
        except Exception as e:
            logger.error(f"Failed to write cookies: {e}")

    # 2. Main Extraction Logic
    try:
        logger.info(f"Processing Request: {url}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "format": "all", 
            "extract_flat": False,
            "referer": "https://www.youtube.com/",
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get("title", "downloaded_file")
            
            # Universal formats collection
            raw_formats = info.get("formats", [info])
            processed_formats = []

            for f in raw_formats:
                f_url = f.get("url")
                if not f_url: continue

                # Platform checking (YouTube, FB, TikTok)
                is_video = f.get("vcodec") != "none" or "fbcdn" in f_url or "tiktok" in f_url or f.get("ext") == "mp4"
                
                if is_video:
                    try:
                        # Force download link modification
                        parsed_url = urlparse(f_url)
                        query_params = parse_qs(parsed_url.query)
                        query_params['mime'] = ['application/octet-stream']
                        new_query = urlencode(query_params, doseq=True)
                        force_download_url = urlunparse(parsed_url._replace(query=new_query))
                    except:
                        force_download_url = f_url

                    processed_formats.append({
                        "format_id": f.get("format_id", "best"),
                        "ext": f.get("ext", "mp4"),
                        "format_note": f.get("format_note") or f.get("quality_label") or "HD",
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "url": f_url,
                        "force_download_url": force_download_url,
                        "resolution": f.get("resolution") or f"{f.get('height')}p" or "Standard",
                        "has_audio": f.get("acodec") != "none" or "fbcdn" in f_url
                    })

            # Duplicate resolutions saaf karna
            unique_formats = {res['resolution']: res for res in processed_formats}.values()
            sorted_formats = sorted(unique_formats, key=lambda x: str(x['resolution']), reverse=True)

            if not sorted_formats:
                raise Exception("No downloadable formats found.")

            return {
                "title": video_title,
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "extractor": info.get("extractor"),
                "formats": list(sorted_formats),
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"Final Extraction Error: {error_msg}")
        
        # User friendly error conversion
        friendly_error = error_msg
        if "confirm you’re not a bot" in error_msg.lower():
            friendly_error = "YouTube Blocked this request. Please update Cookies."
        
        raise HTTPException(status_code=400, detail=friendly_error)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
