# Contradiction Clipper

**A powerful, automated local tool to detect and expose contradictions across multiple video sources.**

---

## 📝 What is Contradiction Clipper?

Contradiction Clipper automates the extraction of contradictory statements from multiple videos (e.g., political pundits, public figures) by:

- Downloading videos from provided URLs.
- Transcribing videos into timestamped segments using Whisper AI.
- Embedding transcript segments to semantically identify contradictions.
- Detecting contradictions via Natural Language Inference (NLI).
- Compiling top contradictions into a concise, impactful video montage.

---

## 🚀 Quick Start

### 🐳 Docker (Preferred)

Build the Docker image (installs all Python requirements and executes
`install_whisper.sh` automatically):

```
docker build -t contradiction-clipper .
```

Run the pipeline (mount the working directory so results persist):

```
    docker run --rm -v "$PWD":/app contradiction-clipper \
        python contradiction_clipper.py --video_list urls.txt \
        --transcribe --embed --detect --compile
    # The container will run install_whisper.sh automatically if the
    # whisper binary or model are missing in the mounted directory.
```

---

### 📦 Manual Installation

#### Dependencies
- Python 3.x
- `yt-dlp`
- `ffmpeg` (required for audio conversion and video processing)
- `whisper.cpp` (required for `--transcribe`)
- `sentence-transformers`
- `transformers`
- `moviepy` (version `~=1.0` with FFmpeg installed, required only for `--compile`)
- `Flask` (for the optional dashboard)
- The NLI model (`roberta-large-mnli`) is automatically downloaded by `transformers`
- NLI models are cached in memory during detection for faster repeated runs

#### Installation

**Step 1: Clone the repository**

        git clone <your_repo_url>
        cd ContradictionClipper

**Step 2: Install Python dependencies**

        pip install -r requirements.txt
        # all Python dependencies are pinned in requirements.txt

**Step 3: Set up Whisper (or use Docker)**

        ./install_whisper.sh

        # This builds whisper.cpp and downloads the default model to ./models
        # The script copies the whisper-cli binary to ./whisper for use by
        # the pipeline.
        # If the binary lives elsewhere, pass its path via --whisper-bin
        # If you skip this step, the pipeline will automatically run the
        # script when transcription is requested.
        # On macOS the script builds with Metal support and disables
        # unsupported ARM instructions automatically.

Docker users may skip Steps 2 and 3 after building the image because it installs
dependencies and runs `install_whisper.sh` automatically.

Ensure `ffmpeg` is installed and available in your system PATH.
If you plan to build Whisper yourself (outside Docker), install the
`libavcodec-dev`, `libavformat-dev`, and `libavutil-dev` packages so the
binary can decode common formats like MP4.

### Transcription

When running the pipeline with `--transcribe`, the Whisper binary is
invoked with `--model models/ggml-base.en.bin -f <video>` so the English
base model is always used. If the transcript JSON file is not created,
Whisper's stdout and stderr are logged to help diagnose the issue.


---

## 🎯 Usage

1. Create `urls.txt` with one YouTube video URL per line:

		https://www.youtube.com/watch?v=VIDEO_ID_1
		https://www.youtube.com/watch?v=VIDEO_ID_2

2. Run the entire pipeline (download, transcribe, embed, detect contradictions, and compile montage):

                ./contradiction_clipper.py --video_list urls.txt --transcribe --embed --detect --compile --top_n 20 --max_workers 4
                # add --whisper-bin /path/to/whisper if the binary lives elsewhere
                # set --log-level DEBUG for more verbose logs

The resulting video montage will be located in:

        output/contradiction_montage.mp4

3. Launch the dashboard to browse videos, transcripts, and contradictions:

                ./contradiction_clipper.py --dashboard

---

## 🗂️ Project Structure

- **videos/**
	- **raw/**: Original downloaded videos.
	- **processed/**: Extracted video snippets for contradictions.
- **transcripts/**: JSON-formatted Whisper transcripts.
- **db/**: SQLite databases for transcripts, embeddings, contradictions.
- **logs/**: Logging outputs for troubleshooting.
- **output/**: Final montage video output.
- **whisper**: Binary of Whisper.cpp for transcription.

---

## Database Schema

Contradiction Clipper stores its data in an SQLite database. A `schema_version`
table tracks migrations so newer releases can upgrade the schema safely. The
current schema version is `2`.

Version 2 introduces a dedicated `files` table keyed by SHA256 hashes. Each
row represents a unique downloaded file and is referenced by entries in the
`videos` table.

---

## 🛠️ Command-Line Arguments

- `--video_list`: Path to URLs list.
- `--transcribe`: Transcribe downloaded videos with Whisper.
- `--whisper-bin`: Path to the Whisper binary (default: `./whisper`).
- `--embed`: Generate semantic embeddings.
- `--detect`: Detect contradictions.
- `--compile`: Compile detected contradictions into a montage.
- `--dashboard`: Launch a simple Flask dashboard to browse results.
- `--summary`: Output text summaries of contradictions to a file
  (default: `output/contradictions.txt`).
- `--top_n`: Number of contradictions to compile (default: 20).
- `--nli-model`: Hugging Face model path or name for contradiction scoring.
- `--max_workers`: Number of parallel workers for downloading and transcription (default: 4).
- `--log-level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR).

---

## 🧪 Running Tests

To run the unit tests without installing every dependency in `requirements.txt`,
install the few lightweight packages that the tests rely on:

```bash
pip install numpy Flask
```

The tests mock out heavy libraries such as `torch`, `sentence-transformers`, and
`transformers`, so those packages are **not** needed just to execute the test
suite.

---

## 🧩 Extensibility & Contribution

- GUI interfaces (Flask/Electron) for ease-of-use.
- Real-time monitoring capabilities.
- Improved semantic matching algorithms.

Feel free to contribute enhancements or optimizations to expand this tool's potential.

---

## 📄 License

Released under the MIT License.

---

## ✅ Contact

For questions, support, or feature suggestions, contact the project maintainer directly.


