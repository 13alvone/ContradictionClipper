#!/bin/bash
# Clone and build whisper.cpp, placing the binary in the project root.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHISPER_DIR="$ROOT_DIR/whisper.cpp"
WHISPER_BIN="$ROOT_DIR/whisper"

if [ ! -d "$WHISPER_DIR" ]; then
    echo "[i] Cloning whisper.cpp repository..."
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
else
    echo "[i] whisper.cpp already present; pulling latest changes."
    git -C "$WHISPER_DIR" pull --ff-only
fi

cd "$WHISPER_DIR"

MAKE_FLAGS="WHISPER_FFMPEG=1"
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "[i] Nvidia GPU detected; building with CUDA and FFmpeg support."
    MAKE_FLAGS="WHISPER_CUBLAS=1 WHISPER_FFMPEG=1"
else
    echo "[i] Building with FFmpeg support."
fi

echo "[i] Building whisper.cpp"
if [[ "$(uname)" == "Darwin" ]]; then
    CMAKE_ARGS="-DGGML_METAL=ON -DGGML_METAL_USE_BF16=ON -DGGML_METAL_EMBED_LIBRARY=ON -DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8-a -DCMAKE_OSX_ARCHITECTURES=$(uname -m)"
    make $MAKE_FLAGS CMAKE_ARGS="$CMAKE_ARGS"
else
    make $MAKE_FLAGS
fi

echo "[i] Moving binary to $WHISPER_BIN"
cp ./build/bin/whisper-cli "$WHISPER_BIN"
cd "$ROOT_DIR"

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

if [ -f "$WHISPER_BIN" ] && [ -x "$WHISPER_BIN" ]; then
    echo "[i] Whisper installed successfully."
else
    echo "[x] Whisper build failed." >&2
    exit 1
fi
