from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="SaveMedia Backend", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # optional: replace "*" with your Blogger domain
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/getinfo")
def get_info(url: str):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = []
    for f in info.get("formats", []):
        if f.get("url") and f.get("format_note"):
            formats.append({
                "quality": f.get("format_note"),
                "ext": f.get("ext"),
                "filesize": f.get("filesize"),
                "url": f.get("url")
            })

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "formats": formats
    }

@app.get("/")
def root():
    return {"message": "SaveMedia Backend is Running ✅"}
