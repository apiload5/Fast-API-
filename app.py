from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

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

            # ✅ Filter only progressive formats (audio + video combined)
            progressive_formats = [
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "format_note": f.get("format_note"),
                    "filesize": f.get("filesize"),
                    "url": f.get("url"),
                    "resolution": f.get("resolution") or f"{f.get('height')}p",
                }
                for f in info.get("formats", [])
                if f.get("url")
                and f.get("acodec") != "none"
                and f.get("vcodec") != "none"
            ]

            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "formats": progressive_formats,
            }

    except Exception as e:
        return {"error": str(e)}


# --- Local run (for debugging only) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
