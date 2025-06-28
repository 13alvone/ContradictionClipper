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

### 📦 Dependencies:
- Python 3.x
- `yt-dlp`
- `whisper.cpp` (required for `--transcribe`)
- `sentence-transformers`
- `transformers`
- `moviepy` (version `~=1.0` with FFmpeg installed, required only for `--compile`)
- `roberta-large-mnli` (Hugging Face model for contradiction detection)
- `Flask` (for the optional dashboard)

### ⚙️ Installation:

**Step 1: Clone the repository**
	
	git clone <your_repo_url>
        cd ContradictionClipper

**Step 2: Install Python dependencies**

        pip install yt-dlp sentence-transformers transformers moviepy~=1.0 torch torchvision torchaudio roberta-large-mnli Flask
        # moviepy only needed when compiling montages

**Step 3: Setup Whisper (optimized for CPU)**

	git clone https://github.com/ggerganov/whisper.cpp.git
	cd whisper.cpp
	make
	cp ./whisper ../

Ensure `ffmpeg` is installed and available in your system PATH.

---

## 🎯 Usage

1. Create `urls.txt` with one YouTube video URL per line:

		https://www.youtube.com/watch?v=VIDEO_ID_1
		https://www.youtube.com/watch?v=VIDEO_ID_2

2. Run the entire pipeline (download, transcribe, embed, detect contradictions, and compile montage):

                ./contradiction_clipper.py --video_list urls.txt --transcribe --embed --detect --compile --top_n 20 --max_workers 4

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
- `--embed`: Generate semantic embeddings.
- `--detect`: Detect contradictions.
- `--compile`: Compile detected contradictions into a montage.
- `--dashboard`: Launch a simple Flask dashboard to browse results.
- `--summary`: Output text summaries of contradictions to a file
  (default: `output/contradictions.txt`).
- `--top_n`: Number of contradictions to compile (default: 20).
- `--nli-model`: Hugging Face model path or name for contradiction scoring.
- `--max_workers`: Number of parallel workers for downloading and transcription (default: 4).

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


