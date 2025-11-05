from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

# --- FastAPI App Setup ---
app = FastAPI(
    title="SaveMedia Backend",
    version="1.1",
    description="Optimized FastAPI backend for SaveMedia.online — direct downloadable formats only."
)

# --- Restricted CORS setup ---
allowed_origins = [
    "https://savemedia.online",
    "https://www.savemedia.online",
    "https://ticnotester.blogspot.com",
    # Local testing allowed if needed:
    # "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Root route (for test/health check) ---
@app.get("/")
def home():
    return {"message": "✅ SaveMedia Backend running successfully on Railway!"}


# --- Optimized Download Info Endpoint ---
@app.get("/download")
def download_video(url: str = Query(..., description="Video URL to extract downloadable info")):
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "forcejson": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get("title", "downloaded_file")
            progressive_formats = []

            # ✅ Filter only progressive formats (audio + video combined)
            for f in info.get("formats", []):
                original_url = f.get("url")

                if original_url and f.get("acodec") != "none" and f.get("vcodec") != "none":
                    # 🔥 URL Modification Logic for Force Download 🔥
                    try:
                        parsed_url = urlparse(original_url)
                        query_params = parse_qs(parsed_url.query)
                        query_params['mime'] = ['application/octet-stream']

                        new_query = urlencode(query_params, doseq=True)
                        force_download_url = urlunparse(parsed_url._replace(query=new_query))
                    except Exception:
                        force_download_url = original_url

                    progressive_formats.append({
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "format_note": f.get("format_note"),
                        "filesize": f.get("filesize"),
                        "url": original_url,
                        "force_download_url": force_download_url,
                        "resolution": f.get("resolution") or f"{f.get('height')}p",
                        "suggested_filename": f"{video_title}.{f.get('ext')}",
                    })

            # Optional: Sort by resolution (highest first)
            progressive_formats.sort(
                key=lambda x: int(
                    x.get('resolution', '0p').replace('p', '').split('x')[0]
                    if 'p' in x.get('resolution', '0p') else '0'
                ),
                reverse=True
            )

            return {
                "title": video_title,
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "formats": progressive_formats,
            }

    except Exception as e:
        error_message = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"Error processing URL: {error_message}")


# --- Local run (for debugging only) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
