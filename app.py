from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from utils.downloader import get_video_info

app = FastAPI(title="SaveMedia Backend", version="1.0")

# ✅ Allowed frontends
origins = [
    "https://savemedia.online",
    "https://ticnotester.blogspot.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Welcome to SaveMedia Backend 🚀"}

@app.get("/api/getVideo")
async def get_video(url: str):
    try:
        data = get_video_info(url)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
