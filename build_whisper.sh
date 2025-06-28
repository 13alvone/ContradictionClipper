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
make

echo "[i] Copying binary"
cp ./main "$ROOT_DIR/whisper"

echo "[i] Cleaning up"
cd "$ROOT_DIR"
rm -rf whisper.cpp

echo "[i] Whisper build complete"
