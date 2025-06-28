# Use lightweight Python image
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg git build-essential cmake curl ccache && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Build whisper.cpp and place binary in project root
RUN chmod +x build_whisper.sh && ./build_whisper.sh

CMD ["python", "contradiction_clipper.py"]
