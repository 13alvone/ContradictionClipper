#!/bin/bash
# Robustly build whisper.cpp and place the binary in the project root.
set -euo pipefail
set -x

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "[i] Cloning whisper.cpp repository"
git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git

echo "[i] Building whisper.cpp"
cd whisper.cpp
MAKE_FLAGS="WHISPER_FFMPEG=1"
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "[i] Nvidia GPU detected; building with CUDA and FFmpeg support."
    MAKE_FLAGS="WHISPER_CUBLAS=1 WHISPER_FFMPEG=1"
else
    echo "[i] Building with FFmpeg support."
fi
make $MAKE_FLAGS

echo "[i] Copying binary"
cp ./build/bin/whisper-cli "$ROOT_DIR/whisper"

echo "[i] Cleaning up"
cd "$ROOT_DIR"
rm -rf whisper.cpp

MODEL_DIR="$ROOT_DIR/models"
MODEL_FILE="$MODEL_DIR/ggml-base.en.bin"
if [ ! -f "$MODEL_FILE" ]; then
    echo "[i] Downloading default Whisper model..."
    mkdir -p "$MODEL_DIR"
    curl -L -o "$MODEL_FILE" \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
else
    echo "[i] Whisper model already present"
fi

echo "[i] Whisper build complete"
