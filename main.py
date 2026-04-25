from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from ytdlp_simple import extract_info  # Changed from yt_dlp
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
import asyncio

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
    "http://localhost:8080",
    "http://localhost:3000",  # Local dev
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

# --- Helper function to convert ytdlp-simple output to your format ---
def convert_to_progressive_formats(info_dict: dict, video_title: str):
    """Convert ytdlp-simple format to your original format structure"""
    progressive_formats = []
    
    # ytdlp-simple provides formats in different structure
    formats = info_dict.get('formats', [])
    
    for f in formats:
        # Check if it's progressive (both audio and video)
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            original_url = f.get('url')
            
            # Your original force download URL modification logic
            try:
                parsed_url = urlparse(original_url)
                query_params = parse_qs(parsed_url.query)
                query_params['mime'] = ['application/octet-stream']
                new_query = urlencode(query_params, doseq=True)
                force_download_url = urlunparse(parsed_url._replace(query=new_query))
            except Exception:
                force_download_url = original_url
            
            # Get resolution
            height = f.get('height', 0)
            resolution = f.get('resolution', f"{height}p" if height else "Unknown")
            
            progressive_formats.append({
                "format_id": f.get('format_id', 'unknown'),
                "ext": f.get('ext', 'mp4'),
                "format_note": f.get('format_note', ''),
                "filesize": f.get('filesize'),
                "url": original_url,
                "force_download_url": force_download_url,
                "resolution": resolution,
                "suggested_filename": f"{video_title}.{f.get('ext', 'mp4')}",
            })
    
    # Sort by resolution (highest first)
    progressive_formats.sort(
        key=lambda x: int(
            x.get('resolution', '0p').replace('p', '').split('x')[0]
            if 'p' in x.get('resolution', '0p') else '0'
        ),
        reverse=True
    )
    
    return progressive_formats

# --- Optimized Download Info Endpoint (ASYNC for better performance) ---
@app.get("/download")
async def download_video(url: str = Query(..., description="Video URL to extract downloadable info")):
    try:
        # ytdlp-simple extract_info is async
        info = await extract_info(url)
        
        video_title = info.get('title', 'downloaded_file')
        
        # Convert formats to your original structure
        progressive_formats = convert_to_progressive_formats(info, video_title)
        
        return {
            "title": video_title,
            "thumbnail": info.get('thumbnail'),
            "uploader": info.get('uploader', 'Unknown'),
            "duration": info.get('duration'),
            "formats": progressive_formats,
        }
        
    except Exception as e:
        error_message = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"Error processing URL: {error_message}")

# --- Alternative: Sync version if async doesn't work ---
@app.get("/download-sync")
def download_video_sync(url: str = Query(...)):
    """Sync version (not recommended, kept for compatibility)"""
    try:
        # Run async function in sync context
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        info = loop.run_until_complete(extract_info(url))
        loop.close()
        
        video_title = info.get('title', 'downloaded_file')
        progressive_formats = convert_to_progressive_formats(info, video_title)
        
        return {
            "title": video_title,
            "thumbnail": info.get('thumbnail'),
            "uploader": info.get('uploader', 'Unknown'),
            "duration": info.get('duration'),
            "formats": progressive_formats,
        }
        
    except Exception as e:
        error_message = str(e).split('\n')[0]
        raise HTTPException(status_code=400, detail=f"Error processing URL: {error_message}")

# --- Additional info endpoint for debugging ---
@app.get("/info")
async def get_info(url: str = Query(...)):
    """Get raw info from ytdlp-simple (for debugging)"""
    try:
        info = await extract_info(url)
        return {
            "success": True,
            "title": info.get('title'),
            "duration": info.get('duration'),
            "platform": info.get('extractor_key', 'unknown'),
            "formats_count": len(info.get('formats', [])),
            "warnings": info.get('warnings', [])  # Shows if used Invidious fallback
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
