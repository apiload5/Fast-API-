import yt_dlp

def get_video_info(url: str):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []

        for f in info.get("formats", []):
            if f.get("url"):
                formats.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f.get("format_note") or f.get("height"),
                    "filesize": f.get("filesize"),
                    "url": f.get("url")
                })

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats
        }
