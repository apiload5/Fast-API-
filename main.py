from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import logging
import random
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="SaveMedia API", version="3.5")

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
    
    # ✅ Vercel Settings se Proxy uthayen (Agar block ho to Proxy kaam karegi)
    proxy_url = os.getenv("PROXY_URL") 
    
    if cookies_data:
        try:
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_data.strip())
        except: pass

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
            
            # ✅ Sabse takatwar User-Agents rotate karein
            "user_agent": random.choice([
                "com.google.android.youtube/19.12.35 (Linux; U; Android 14; en_US; Pixel 7 Pro) gzip",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ]),
            
            "format": "best[ext=mp4]/best",
            "nocheckcertificate": True,
            "geo_bypass": True,
            
            # ✅ Proxy configuration (Automated)
            "proxy": proxy_url if proxy_url else None,
            
            # ✅ IPv6 force (Bypass trick)
            "source_address": "::", 

            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "tvhtml5"],
                    "player_skip": ["webpage", "configs"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = info.get("formats", [info])
            processed = []

            for f in formats:
                f_url = f.get("url")
                if not f_url: continue

                is_youtube = "youtube" in url or "youtu.be" in url
                has_both = f.get("vcodec") != "none" and f.get("acodec") != "none"

                if (is_youtube and has_both) or (not is_youtube and f.get("vcodec") != "none"):
                    res = f.get("resolution") or (f"{f.get('height')}p" if f.get('height') else "HD")
                    
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

            unique_list = {res['resolution']: res for res in processed}.values()
            final_formats = sorted(unique_list, key=lambda x: str(x['resolution']), reverse=True)

            return {
                "title": info.get("title", "Video"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": list(final_formats),
                "using_proxy": bool(proxy_url)
            }

    except Exception as e:
        error_msg = str(e).split('\n')[0]
        # Agar IPv6 fail ho to IPv4 par fallback karein (Vercel Compatibility)
        if "network is unreachable" in error_msg.lower() and "::" in str(e):
            logger.info("IPv6 failed, retrying with IPv4...")
            # Yahan logic repeat karne ki bajaye simple error return karein ya retry function dalen
        
        logger.error(f"API Error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
