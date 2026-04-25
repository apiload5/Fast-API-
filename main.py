from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# --- Vercel Logs Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(
    title="SaveMedia Backend",
    version="2.0",
    description="Final Optimized Version for SaveMedia.online"
)

# --- Restricted CORS ---
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
    return {"message": "✅ SaveMedia API is Live and Optimized!"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL to extract")):
    # 1. Setup Cookies
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except Exception as e:
            logger.error(f"Cookie write error: {e}")

    try:
        logger.info(f"Extracting: {url}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "format": "all", 
            "extract_flat": False,
            "referer": "https://www.youtube.com/",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get("title", "downloaded_file")
            
            raw_formats = info.get("formats", [info])
            processed_formats = []

            for f in raw_formats:
                f_url = f.get("url")
                if not f_url: continue

                # ✅ Aggressive Filtering: YouTube, FB, TikTok
                # Har wo format uthayenge jis mein video stream ho ya ext mp4/webm ho
                is_video = (
                    f.get("vcodec") != "none" or 
                    f.get("ext") in ["mp4", "webm", "m4v"] or
                    "fbcdn" in f_url or 
                    "tiktok" in f_url
                )
                
                if is_video:
                    # Resolution detection
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "Standard")
                    
                    try:
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
                        "resolution": res,
                        "has_audio": f.get("acodec") != "none" or "fbcdn" in f_url
                    })

            # Duplicate resolutions saaf kar ke sort karein
            unique_formats = {res['resolution']: res for res in processed_formats}.values()
            sorted_formats = sorted(unique_formats, key=lambda x: str(x['resolution']), reverse=True)

            if not sorted_formats:
                 raise Exception("YouTube hidden formats. Please update cookies.")

            return {
                "title": video_title,
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(sorted_formats),
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"API Error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
