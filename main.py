from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Union, Optional
import yt_dlp
import uuid
import os
from fastapi.responses import FileResponse, RedirectResponse

# --- Configuration & Security ---

# Sirf in URLs se aane wali requests allow hongi (Referer Header Check)
ALLOWED_REFERERS = [
    "https://crispy0921.blogspot.com",
    "https://crispy0921.blogspot.com/?m=1", 
    # Agar aapka blogspot domain change ho to yahan add karein
]

# Ad Page URL jahan har download ke baad redirect/new tab khulega
AD_PAGE_URL = "https://www.example.com/your-ad-page" 

# Storage aur Queue (Production mein Redis/Celery se badla jayega)
DOWNLOAD_QUEUE = {} 
DOWNLOAD_FOLDER = "downloads"
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True) # exist_ok=True taake error na aaye

app = FastAPI(
    title="Secure Multi-Platform Downloader Backend",
    description="Backend with Referer-based security and temporary storage."
)

# Pydantic Model for User Input
class LinkInput(BaseModel):
    video_url: HttpUrl

class FormatDetails(BaseModel):
    format_id: str
    resolution: str
    extension: str
    filesize_estimate: Optional[int] = None

# ----------------- Security: Global Dependency (Referer Check) -----------------

def check_referer(referer: Optional[str] = Header(None)):
    """Check karta hai ke request sirf allowed blogspot domain se aayi hai."""
    if not referer:
        # Referer header na hone par (misal ke taur par, direct access)
        raise HTTPException(status_code=403, detail="Access denied: Referer header missing.")
    
    # Simple check: agar referer allowed list mein shamil ho
    is_allowed = any(referer.startswith(domain) for domain in ALLOWED_REFERERS)
    
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied: Unauthorized source.")
    
    return True # Agar check pass ho gaya

# ----------------- Helper Function: yt-dlp se Data nikalna -----------------

def get_video_metadata(url: str) -> Dict:
    """yt-dlp ka istemal karke sirf video ki information nikalna."""
    ydl_opts = {
        'skip_download': True,
        'force_generic_extractor': True,
        'quiet': True,
        'simulate': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or unsupported link: {str(e)}")

# ----------------- Background Download Worker -----------------

def start_download_worker(job_id: str, url: str, format_id: str):
    """File ko server par aarzi taur par download karta hai."""
    DOWNLOAD_QUEUE[job_id] = {"status": "Processing", "progress": 0, "file_path": None, "url": url}
    
    try:
        # Output file ka naam tayyar karna (Job ID se)
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{job_id}.%(ext)s")

        ydl_opts = {
            'format': format_id,
            'outtmpl': output_template,
            'quiet': True,
            'noplaylist': True,
            # 'retries': 10, # Production mein yeh options bahut zaroori hain!
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info_dict)

        DOWNLOAD_QUEUE[job_id]["status"] = "Completed"
        DOWNLOAD_QUEUE[job_id]["file_path"] = downloaded_file
        
    except Exception as e:
        DOWNLOAD_QUEUE[job_id]["status"] = "Failed"
        DOWNLOAD_QUEUE[job_id]["error"] = str(e)

# ----------------- API End Points -----------------

@app.post("/scan-link/", dependencies=[Depends(check_referer)], response_model=Dict[str, Union[str, List[FormatDetails]]], status_code=200)
async def scan_video_link(input_data: LinkInput):
    """Link ko scan karta hai, thumbnail aur available formats deta hai."""
    url = str(input_data.video_url)
    info = get_video_metadata(url)

    thumbnail_url = info.get('thumbnail') or info.get('thumbnails', [{}])[-1].get('url')
    available_formats: List[FormatDetails] = []
    
    # Logic for MP3/Audio
    best_audio = next((f for f in info.get('formats', []) if f.get('acodec') != 'none'), None)
    if best_audio and 'mp3' not in [fmt.resolution for fmt in available_formats]:
        available_formats.append(FormatDetails(
            format_id=best_audio.get('format_id') or 'bestaudio', 
            resolution='MP3 (Audio Only)', 
            extension='mp3',
            filesize_estimate=best_audio.get('filesize_approx')
        ))

    # Logic for Video Formats (Standard Resolutions)
    for f in info.get('formats', []):
        resolution = f.get('height')
        if f.get('vcodec') != 'none' and resolution and resolution in [144, 240, 360, 480, 720, 1080]:
            
            resolution_tag = f"{resolution}p"
            if resolution == 1080:
                 resolution_tag += " (Premium)" # Label for Premium
                 
            # Duplicate resolutions ko avoid karna
            if resolution_tag not in [fmt.resolution for fmt in available_formats]:
                available_formats.append(FormatDetails(
                    format_id=f.get('format_id'),
                    resolution=resolution_tag,
                    extension=f.get('ext') or 'mp4',
                    filesize_estimate=f.get('filesize_approx')
                ))
    
    return {
        "title": info.get('title', 'Unknown Video'),
        "thumbnail_url": thumbnail_url,
        "available_formats": available_formats
    }

@app.post("/download-request/", dependencies=[Depends(check_referer)])
async def request_download(input_data: LinkInput, format_id: str, background_tasks: BackgroundTasks):
    """Download request ko queue mein daalta hai aur Job ID return karta hai."""
    job_id = str(uuid.uuid4())
    url = str(input_data.video_url)

    # Background task mein download worker shuru karna
    background_tasks.add_task(start_download_worker, job_id, url, format_id)
    
    return {"job_id": job_id, "status": "Download started in background.", "check_url": f"/status/{job_id}"}


@app.get("/status/{job_id}", dependencies=[Depends(check_referer)])
async def get_download_status(job_id: str):
    """User ko download ka status batana (Poling ke liye)"""
    if job_id not in DOWNLOAD_QUEUE:
        raise HTTPException(status_code=404, detail="Job ID not found or expired.")
    
    return DOWNLOAD_QUEUE[job_id]


@app.get("/get-file/{job_id}")
async def serve_download(job_id: str, background_tasks: BackgroundTasks):
    """
    Final file serve karta hai aur use user ke computer/mobile mein download karvata hai.
    NOTE: Is endpoint par Referer check nahi lagaya gaya hai, kyonke download link aksar 
    browser ke naye process se khulta hai jismein Referer header nahi hota. Lekin yeh link
    sirf ek baar hi istemal hoga kyonke file delete ho jayegi.
    """
    if job_id not in DOWNLOAD_QUEUE or DOWNLOAD_QUEUE[job_id].get("status") != "Completed":
        # Agar job complete na ho ya ID mojud na ho
        return RedirectResponse(AD_PAGE_URL, status_code=302) # Phir bhi ad page par bhej den

    job = DOWNLOAD_QUEUE[job_id]
    file_path = job["file_path"]

    # File serve hone ke baad delete karna aur queue se hatana
    def cleanup():
        try:
            os.remove(file_path)
            if job_id in DOWNLOAD_QUEUE:
                del DOWNLOAD_QUEUE[job_id] 
        except Exception as e:
            print(f"Cleanup error for {job_id}: {e}")

    # Cleanup function ko file bhejte hi call karna
    background_tasks.add_task(cleanup)
    
    # FileResponse client ko file download karne ko majboor karti hai
    return FileResponse(
        path=file_path, 
        filename=os.path.basename(file_path),
        media_type='application/octet-stream', # Download prompt ke liye zaroori
    )
