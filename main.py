from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/download")
async def download_video(url: str = Query(...)):
    cookie_path = "/tmp/cookies.txt"
    cookies_data = os.getenv("COOKIES_CONTENT")
    
    if cookies_data:
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookies_data.strip())

    try:
        # ✅ FINAL OPTIMIZED YDL_OPTS
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "format": "best",
            "geo_bypass": True,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "skip": ["dash", "hls"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Simple format extraction
            formats = info.get("formats", [])
            processed = []
            for f in formats:
                if f.get("url") and (f.get("vcodec") != "none" or "tiktok" in f.get("url")):
                    processed.append({
                        "resolution": f.get("resolution") or f"{f.get('height')}p",
                        "url": f.get("url"),
                        "ext": f.get("ext")
                    })

            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "formats": processed
            }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=400, detail="Extraction Failed. Check Logs.")
