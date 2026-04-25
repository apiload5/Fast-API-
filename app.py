from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# --- Vercel Logs Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SaveMedia Backend",
    version="1.6",
    description="Final Optimized Backend for SaveMedia.online"
)

# --- Restricted CORS (As per your request) ---
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
    return {"message": "✅ SaveMedia Backend is fully operational!"}

@app.get("/download")
def download_video(url: str = Query(..., description="Video URL to extract")):
    # 1. Cookies Extraction (Vercel Environment Variable se)
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w") as f:
                f.write(cookies_data)
            logger.info("Cookies file created successfully in /tmp")
        except Exception as e:
            logger.error(f"Error writing cookies: {e}")

    try:
        logger.info(f"Attempting to extract info for: {url}")

        # 2. Universal yt-dlp Configuration
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            # 'best' use karne se Facebook ke direct links asani se milte hain
            "format": "best", 
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get("title", "downloaded_file")
            
            # YouTube ke liye formats list hoti hai, Facebook ke liye kabhi direct info hoti hai
            raw_formats = info.get("formats", [info])
            processed_formats = []

            for f in raw_formats:
                f_url = f.get("url")
                if not f_url:
                    continue

                # Video filter (vcodec 'none' na ho ya FB ki CDN link ho)
                is_video = f.get("vcodec") != "none" or "fbcdn" in f_url or "facebook.com" in f_url
                
                if is_video:
                    # Force download logic (Mime type change)
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
                        "resolution": f.get("resolution") or f"{f.get('height')}p" or "Standard",
                        "has_audio": f.get("acodec") != "none" or "fbcdn" in f_url
                    })

            # Duplicate resolutions saaf karna aur sort karna
            unique_formats = {res['resolution']: res for res in processed_formats}.values()
            sorted_formats = sorted(unique_formats, key=lambda x: str(x['resolution']), reverse=True)

            return {
                "title": video_title,
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "source": info.get("extractor_key"),
                "formats": list(sorted_formats),
            }

    except Exception as e:
        error_detail = str(e).split('\n')[0]
        logger.error(f"Extraction failed for {url}: {error_detail}")
        
        # User-friendly error messages
        clean_error = "Error processing video."
        if "confirm you’re not a bot" in error_detail.lower():
            clean_error = "YouTube block. Update cookies in Vercel settings."
        elif "Unsupported URL" in error_detail:
            clean_error = "Platform not supported."
        else:
            clean_error = error_detail.split(':')[-1].strip()

        raise HTTPException(status_code=400, detail=clean_error)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
