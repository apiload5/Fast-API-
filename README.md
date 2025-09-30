# High-Scale Multi-Platform Video Downloader Backend 🚀

Yeh backend application Python (FastAPI) aur yt-dlp ka istemal karte hue videos download karta hai. Ismein Referer Header check ki madad se API security shamil hai.

## Features
- **Multi-Platform Support:** `yt-dlp` ki madad se kai platforms ko support karta hai.
- **Scalability:** FastAPI aur Docker ke saath design kiya gaya hai (million users ke liye).
- **Temporary Storage:** File ko user ke computer ya mobile mein direct download karwaya jata hai taake server storage use na ho.
- **Monetization:** Har download se pehle custom ad page par redirect karna.
- **Security:** Sirf allowed blogspot domain (`crispy0921.blogspot.com`) se aane wali requests allow hain.

## Setup (Replit/Local)

1. **Clone the Repository:**
   ```bash
   git clone [Your Repository URL]
   cd video-downloader-backend
