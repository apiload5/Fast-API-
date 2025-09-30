# Base image (Python ki halki image)
FROM python:3.10-slim

# Working directory set karna
WORKDIR /app

# Dependencies install karna (Linux aur yt-dlp ke liye zaroori)
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies copy aur install karna
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application files copy karna
COPY . .

# Download folder banana
RUN mkdir -p /app/downloads

# FastAPI application run karne ke liye default command
# Bind address 0.0.0.0 aur port 8000 (ya koi bhi)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
