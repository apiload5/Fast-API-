from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.0")

# ✅ Restricted CORS for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://savemedia.online",
        "https://www.savemedia.online",
        "https://ticnotester.blogspot.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/download")
async def extract_video(url: str = Query(..., description="Video URL")):
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except Exception as e:
            logger.error(f"Cookie Error: {e}")

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            
            # ✅ Sabse Ahem: 'best' use karein taake FFmpeg ki zaroorat na pare (Vercel Fix)
            "format": "best[ext=mp4]/best", 
            
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web", "ios"],
                    "player_skip": ["webpage", "configs"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Handle formats safely
            raw_formats = info.get("formats", [info])
            processed = []

            for f in raw_formats:
                f_url = f.get("url")
                if not f_url: continue

                # ✅ Sirf wo formats jin mein Audio + Video dono pehle se merged hon
                has_video = f.get("vcodec") != "none"
                has_audio = f.get("acodec") != "none"
                
                if (has_video and has_audio) or "fbcdn" in f_url or "tiktok" in f_url:
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "HD")
                    
                    # Force download link generator
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

            # Sort and unique
            unique_list = {res['resolution']: res for res in processed}.values()
            final_formats = sorted(unique_list, key=lambda x: str(x['resolution']), reverse=True)

            if not final_formats:
                raise Exception("YouTube hidden formats. Please check cookies.")

            return {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(final_formats)
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        logger.error(f"API Error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
