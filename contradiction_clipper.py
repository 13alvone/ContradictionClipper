"""Core pipeline for the Contradiction Clipper project."""
# pylint: disable=import-error, consider-using-f-string, broad-exception-caught

import argparse
import hashlib
import logging
import numpy as np
import os
import sqlite3
import subprocess
import sys
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import dashboard

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

DB_PATH = "db/contradictions.db"
SCHEMA_VERSION = 2

# Cached sentence-transformer models
_EMBED_MODELS = {}


def ensure_whisper_installed(whisper_bin):
    """Build whisper.cpp and download the model if missing."""
    script = os.path.join(os.path.dirname(__file__), "install_whisper.sh")
    if os.path.isfile(whisper_bin) and os.path.isfile(os.path.join("models", "ggml-base.en.bin")):
        return True
    if not os.path.isfile(script):
        logging.error("[x] install_whisper.sh not found: %s", script)
        return False
    logging.info("[i] Running install_whisper.sh to set up Whisper.")
    result = subprocess.run([script], capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("[x] install_whisper.sh failed: %s", result.stderr.strip())
        return False
    return os.path.isfile(whisper_bin) and os.path.isfile(os.path.join("models", "ggml-base.en.bin"))


def get_schema_version(conn):
    """Return the current schema version, or 0 if table missing."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def migrate_db(conn, target_version=SCHEMA_VERSION):
    """Apply migrations up to the target schema version."""
    current = get_schema_version(conn)
    cursor = conn.cursor()
    if current == 0:
        init_db(conn)
        current = SCHEMA_VERSION
    if current < target_version:
        # Placeholder for future migrations
        cursor.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
            (target_version, datetime.utcnow().isoformat()),
        )
        conn.commit()
    elif current > target_version:
        raise RuntimeError(
            "Database schema version "
            f"{current} newer than supported {target_version}"
        )


def init_db(conn):
    """Create required tables with UNIQUE constraints."""
    logging.info("[i] Initializing database schema.")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            sha256 TEXT PRIMARY KEY,
            video_id TEXT,
            file_path TEXT,
            size_bytes INTEGER,
            hash_ts TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            file_hash TEXT,
            dl_timestamp TEXT,
            FOREIGN KEY(file_hash) REFERENCES files(sha256)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            segment_start REAL,
            segment_end REAL,
            text TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript_id INTEGER UNIQUE,
            embedding BLOB,
            created_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS contradictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_a_id INTEGER,
            segment_b_id INTEGER,
            confidence REAL,
            UNIQUE(segment_a_id, segment_b_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT
        )
        """
    )
    conn.commit()
    if get_schema_version(conn) == 0:
        cursor.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.utcnow().isoformat()),
        )
        conn.commit()


def hash_file(path):
    """Return SHA256 hash of a file."""
    logging.debug("[DEBUG] Hashing file %s", path)
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_video(url):
    """Download a video using yt-dlp and return the local path and video id."""
    logging.info("[i] Downloading video from %s", url)
    os.makedirs("videos/raw", exist_ok=True)
    vid_res = subprocess.run(
        ["yt-dlp", "--get-id", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if vid_res.returncode != 0:
        logging.error("[x] Failed to get video id: %s", vid_res.stderr.strip())
        raise RuntimeError(vid_res.stderr.strip())
    video_id = vid_res.stdout.strip()
    logging.debug("[DEBUG] Video id %s resolved for %s", video_id, url)
    template = f"videos/raw/{video_id}.%(ext)s"
    res = subprocess.run(
        ["yt-dlp", "-f", "best", "-o", template, url],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        logging.error("[x] Download failed: %s", res.stderr.strip())
        raise RuntimeError(res.stderr.strip())
    for ext in ["mp4", "mkv", "webm", "flv", "mov"]:
        candidate = os.path.join("videos/raw", f"{video_id}.{ext}")
        if os.path.exists(candidate):
            logging.info("[i] Video downloaded to %s", candidate)
            return candidate, video_id
    logging.error("[x] Unable to locate downloaded file for %s", url)
    raise FileNotFoundError(f"Unable to locate downloaded file for {url}")


def process_videos(video_list_path, db_path=DB_PATH, max_workers=4):
    """Download videos, compute hashes and record them if unseen."""
    logging.info("[i] Processing videos with %s workers.", max_workers)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    migrate_db(conn)
    cursor = conn.cursor()

    with open(video_list_path, "r", encoding="utf-8") as f:
        raw_urls = [line.strip() for line in f if line.strip()]

    urls = []
    for url in raw_urls:
        cursor.execute("SELECT id FROM videos WHERE url=?", (url,))
        if cursor.fetchone():
            logging.info("[!] Already processed URL, skipping: %s", url)
            continue
        if url not in urls:
            urls.append(url)

    def worker(url):
        thread_name = threading.current_thread().name
        conn_w = sqlite3.connect(db_path, check_same_thread=False)
        conn_w.execute("PRAGMA journal_mode=WAL")
        cur = conn_w.cursor()
        try:
            cur.execute("SELECT id FROM videos WHERE url=?", (url,))
            if cur.fetchone():
                logging.info(
                    "[!] [%s] Already processed URL, skipping: %s",
                    thread_name,
                    url,
                )
                return

            logging.info("[i] [%s] Downloading %s", thread_name, url)
            path, vid = download_video(url)
            file_hash = hash_file(path)

            cur.execute("SELECT 1 FROM files WHERE sha256=?", (file_hash,))
            file_exists = cur.fetchone() is not None

            try:
                cur.execute(
                    (
                        "INSERT INTO files (sha256, video_id, file_path, "
                        "size_bytes, hash_ts) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        file_hash,
                        vid,
                        path,
                        os.path.getsize(path),
                        datetime.utcnow().isoformat(),
                    ),
                )
                logging.info("[i] [%s] Stored file %s", thread_name, vid)
            except sqlite3.IntegrityError:
                logging.info(
                    "[!] [%s] Duplicate video content for %s; "
                    "using existing file",
                    thread_name,
                    url,
                )
                os.remove(path)
                file_exists = True

            try:
                cur.execute(
                    "INSERT INTO videos (url, file_hash, dl_timestamp) "
                    "VALUES (?, ?, ?)",
                    (url, file_hash, datetime.utcnow().isoformat()),
                )
                conn_w.commit()
                logging.info("[i] [%s] Recorded URL %s", thread_name, url)
            except sqlite3.IntegrityError:
                logging.info(
                    "[!] [%s] URL already recorded %s", thread_name, url
                )
                if not file_exists:
                    os.remove(path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "[x] [%s] Failed to process %s: %s", thread_name, url, exc
            )
        finally:
            conn_w.close()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(worker, urls)

    conn.close()


def transcribe_videos(db_conn, whisper_bin="./whisper", max_workers=4):
    """Transcribe new videos with whisper.

    Populate the transcripts table.
    """
    logging.info("[i] Transcribing videos with %s workers.", max_workers)
    model_file = os.path.join("models", "ggml-base.en.bin")
    if not os.path.isfile(whisper_bin) or not os.path.isfile(model_file):
        if not ensure_whisper_installed(whisper_bin):
            logging.error("[x] Whisper setup failed. Cannot transcribe.")
            return
    db_conn.execute("PRAGMA journal_mode=WAL")
    cursor = db_conn.cursor()
    cursor.execute("SELECT video_id, file_path FROM files")
    videos = cursor.fetchall()

    os.makedirs("transcripts", exist_ok=True)

    db_path = db_conn.execute("PRAGMA database_list").fetchone()[2]

    def worker(item):
        vid, path = item
        thread_name = threading.current_thread().name
        conn_w = sqlite3.connect(db_path, check_same_thread=False)
        conn_w.execute("PRAGMA journal_mode=WAL")
        cur = conn_w.cursor()
        cur.execute("SELECT 1 FROM transcripts WHERE video_id=?", (vid,))
        if cur.fetchone():
            logging.info(
                "[!] [%s] Transcript already exists for %s, skipping.",
                thread_name,
                vid,
            )
            conn_w.close()
            return

        out_json = os.path.join("transcripts", f"{vid}.json")
        result = subprocess.run(
            [
                whisper_bin,
                path,
                "--model",
                "models/ggml-base.en.bin",
                "-oj",
                "--output-file",
                os.path.join("transcripts", vid),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logging.error(
                "[x] [%s] Whisper failed for %s: %s",
                thread_name,
                vid,
                result.stderr.strip(),
            )
            conn_w.close()
            return
        if not os.path.exists(out_json):
            logging.error(
                "[x] [%s] Transcript output missing for %s", thread_name, vid
            )
            logging.error(
                "[x] [%s] Whisper stdout: %s",
                thread_name,
                result.stdout.strip(),
            )
            logging.error(
                "[x] [%s] Whisper stderr: %s",
                thread_name,
                result.stderr.strip(),
            )
            conn_w.close()
            return

        try:
            with open(out_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            for seg in data.get("segments", []):
                cur.execute(
                    "INSERT INTO transcripts (video_id, segment_start, "
                    "segment_end, text) VALUES (?, ?, ?, ?)",
                    (
                        vid,
                        seg.get("start"),
                        seg.get("end"),
                        seg.get("text"),
                    ),
                )
            conn_w.commit()
            logging.info("[i] [%s] Transcribed %s", thread_name, vid)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "[x] [%s] Failed to store transcript for %s: %s",
                thread_name,
                vid,
                exc,
            )
        finally:
            conn_w.close()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(worker, videos)


def load_embedding_model(model_name="all-MiniLM-L6-v2"):
    """Return a sentence-transformer model, cached for reuse."""
    if model_name in _EMBED_MODELS:
        logging.info("[i] Reusing cached embedding model: %s", model_name)
        return _EMBED_MODELS[model_name]
    from sentence_transformers import SentenceTransformer

    logging.info("[i] Loading embedding model: %s", model_name)
    model = SentenceTransformer(model_name)
    _EMBED_MODELS[model_name] = model
    return model


def embed_transcripts(db_conn, model_name="all-MiniLM-L6-v2"):
    """Generate embeddings for transcripts without existing embeddings."""
    logging.info("[i] Embedding transcripts.")
    cursor = db_conn.cursor()
    cursor.execute("SELECT id, text FROM transcripts")
    rows = cursor.fetchall()

    model = load_embedding_model(model_name)

    for tid, text in rows:
        cursor.execute(
            "SELECT 1 FROM embeddings WHERE transcript_id=?", (tid,)
        )
        if cursor.fetchone():
            logging.info(
                "[!] Embedding exists for transcript %s, skipping.", tid
            )
            continue

        try:
            embedding = model.encode(text, show_progress_bar=False)
            if isinstance(embedding, list) or getattr(embedding, "ndim", 1) > 1:
                embedding = embedding[0]
            emb_blob = np.asarray(embedding, dtype=np.float32).tobytes()
            cursor.execute(
                (
                    "INSERT INTO embeddings "
                    "(transcript_id, embedding, created_at) "
                    "VALUES (?, ?, ?)"
                ),
                (tid, sqlite3.Binary(emb_blob), datetime.utcnow().isoformat()),
            )
            db_conn.commit()
            logging.info("[i] Embedded transcript %s", tid)
        except Exception as exc:
            logging.error("[x] Failed to embed transcript %s: %s", tid, exc)


_NLI_CACHE = {}


def load_nli_model(model_name="roberta-large-mnli"):
    """Return a scoring function using a transformers NLI model.

    Models are cached in-memory so repeated calls with the same name do not
    re-instantiate the tokenizer and model.
    """
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch

    if model_name in _NLI_CACHE:
        logging.info("[i] Reusing cached NLI model: %s", model_name)
        tokenizer, model, contr_idx = _NLI_CACHE[model_name]
    else:
        logging.info("[i] Loading NLI model: %s", model_name)
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        contr_idx = model.config.label2id.get("CONTRADICTION", 0)
        _NLI_CACHE[model_name] = (tokenizer, model, contr_idx)

    def score(text_a, text_b):
        logging.debug(
            "[DEBUG] Scoring contradiction for: %s | %s", text_a, text_b
        )
        inputs = tokenizer(
            text_a, text_b, return_tensors="pt", truncation=True
        )
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1)[0].tolist()
        return float(probs[contr_idx])

    return score


def detect_contradictions(db_conn, nli_model="roberta-large-mnli"):
    """Detect and store contradictions between transcript segments."""
    logging.info("[i] Detecting contradictions.")
    scorer = load_nli_model(nli_model)
    cursor = db_conn.cursor()
    cursor.execute("SELECT id, text FROM transcripts")
    transcripts = cursor.fetchall()

    for i, (id_a, text_a) in enumerate(transcripts):
        for id_b, text_b in transcripts[i + 1:]:
            logging.debug("[DEBUG] Evaluating %s-%s", id_a, id_b)
            cursor.execute(
                (
                    "SELECT 1 FROM contradictions WHERE "
                    "segment_a_id=? AND segment_b_id=?"
                ),
                (id_a, id_b),
            )
            if cursor.fetchone():
                logging.info(
                    "[!] Contradiction already recorded for %s-%s, skipping.",
                    id_a,
                    id_b,
                )
                continue

            try:
                score = scorer(text_a, text_b)
                if score > 0:
                    cursor.execute(
                        (
                            "INSERT INTO contradictions "
                            "(segment_a_id, segment_b_id, confidence) "
                            "VALUES (?, ?, ?)"
                        ),
                        (id_a, id_b, score),
                    )
                    db_conn.commit()
                    logging.info(
                        "[i] Contradiction stored for %s-%s score=%s",
                        id_a,
                        id_b,
                        score,
                    )
            except Exception as exc:
                logging.error(
                    "[x] Failed to evaluate contradiction for %s-%s: %s",
                    id_a,
                    id_b,
                    exc,
                )


def extract_clip(video_path, start_time, end_time, output_path):
    """Extract a subclip from a video file."""
    try:
        from moviepy.editor import VideoFileClip
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ImportError(
            "moviepy is required for extracting clips. "
            "Install it with 'pip install moviepy'."
        ) from exc
    logging.info(
        "[i] Extracting clip: %s (%s-%ss)", video_path, start_time, end_time
    )
    try:
        with VideoFileClip(video_path) as clip:
            snippet = clip.subclip(start_time, end_time)
            snippet.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                verbose=False,
                logger=None,
            )
        logging.info("[i] Successfully extracted: %s", output_path)
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error("[x] Failed to extract clip from %s: %s", video_path, e)
        return False


def compile_contradiction_montage(
    db_conn,
    output_file="output/contradiction_montage.mp4",
    clip_duration=15,
    top_n=20,
):
    """Build a montage video showcasing top contradictions."""
    # pylint: disable=too-many-locals
    try:
        from moviepy.editor import VideoFileClip, concatenate_videoclips
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ImportError(
            "moviepy is required for compiling montages. "
            "Install it with 'pip install moviepy'."
        ) from exc
    logging.info("[i] Compiling contradiction montage video.")
    cursor = db_conn.cursor()

    cursor.execute(
        """
        SELECT
            t1.video_id, t1.segment_start, t1.segment_end,
            t2.video_id, t2.segment_start, t2.segment_end,
            c.confidence
        FROM contradictions c
        JOIN transcripts t1 ON c.segment_a_id = t1.id
        JOIN transcripts t2 ON c.segment_b_id = t2.id
        ORDER BY c.confidence DESC LIMIT ?
    """,
        (top_n,),
    )

    contradictions = cursor.fetchall()
    clips = []

    for idx, (
        vid1,
        start1,
        _end1,
        vid2,
        start2,
        _end2,
        _conf,
    ) in enumerate(contradictions):
        video1_path = f"videos/raw/{vid1}.mp4"
        video2_path = f"videos/raw/{vid2}.mp4"

        clip1_start = max(0, start1 - 2)
        clip1_end = clip1_start + clip_duration
        clip2_start = max(0, start2 - 2)
        clip2_end = clip2_start + clip_duration

        clip1_path = f"videos/processed/contradiction_{idx}_a.mp4"
        clip2_path = f"videos/processed/contradiction_{idx}_b.mp4"

        os.makedirs("videos/processed", exist_ok=True)

        if extract_clip(video1_path, clip1_start, clip1_end, clip1_path):
            clips.append(VideoFileClip(clip1_path))

        if extract_clip(video2_path, clip2_start, clip2_end, clip2_path):
            clips.append(VideoFileClip(clip2_path))

    if not clips:
        logging.warning("[!] No clips extracted. Exiting compilation.")
        return

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        output_file,
        codec="libx264",
        audio_codec="aac",
    )

    logging.info(
        "[i] Contradiction montage successfully created: %s", output_file
    )


def summarize_contradictions(db_conn, output_file="output/contradictions.txt"):
    """Write a human-readable summary of all detected contradictions."""
    logging.info("[i] Generating contradiction summary: %s", output_file)
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT t1.video_id, t1.segment_start, t1.segment_end, t1.text,
               t2.video_id, t2.segment_start, t2.segment_end, t2.text
        FROM contradictions c
        JOIN transcripts t1 ON c.segment_a_id = t1.id
        JOIN transcripts t2 ON c.segment_b_id = t2.id
        ORDER BY c.id
        """
    )
    rows = cursor.fetchall()
    if not rows:
        logging.warning("[!] No contradictions found to summarize.")
        return
    dir_name = os.path.dirname(output_file)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as fh:
        for (
            vid1,
            start1,
            end1,
            text1,
            vid2,
            start2,
            end2,
            text2,
        ) in rows:
            start1 = 0 if start1 is None else start1
            end1 = 0 if end1 is None else end1
            start2 = 0 if start2 is None else start2
            end2 = 0 if end2 is None else end2
            paragraph = (
                f'In video {vid1} at {start1:.1f}-{end1:.1f}s: '
                f'"{text1.strip()}". '
                f'This contradicts video {vid2} at {start2:.1f}-{end2:.1f}s: '
                f'"{text2.strip()}".'
            )
            fh.write(paragraph + "\n")
    logging.info("[i] Summary written to %s", output_file)


def main():
    """Entry point for the CLI utility."""
    logging.info("[i] Starting Contradiction Clipper pipeline.")
    parser = argparse.ArgumentParser(
        description="Contradiction Clipper - Complete Pipeline"
    )
    parser.add_argument(
        "--video_list",
        help="Path to file containing YouTube video URLs (one per line)",
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Transcribe downloaded videos with whisper.",
    )
    parser.add_argument(
        "--whisper-bin",
        default="./whisper",
        help="Path to Whisper binary used for transcription.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate embeddings for transcripts.",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Detect contradictions in transcripts.",
    )
    parser.add_argument(
        "--nli-model",
        default="roberta-large-mnli",
        help="Hugging Face model path or name for NLI.",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Compile detected contradictions into video.",
    )
    parser.add_argument(
        "--top_n",
        type=int,
        default=20,
        help="Number of contradictions to include in the montage.",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=4,
        help="Maximum parallel workers for download and transcription.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch the web dashboard interface.",
    )
    parser.add_argument(
        "--summary",
        nargs="?",
        const="output/contradictions.txt",
        default=None,
        help=(
            "Write text summary of contradictions to optional FILE. "
            "Default file is output/contradictions.txt when flag is used."
        ),
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("[DEBUG] Verbose logging enabled")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db_conn = sqlite3.connect(DB_PATH)
    migrate_db(db_conn)

    if args.video_list:
        if not os.path.exists(args.video_list):
            logging.error(
                "[x] URL list file does not exist: %s", args.video_list
            )
            sys.exit(1)
        process_videos(args.video_list, max_workers=args.max_workers)

    if args.transcribe:
        transcribe_videos(
            db_conn,
            whisper_bin=args.whisper_bin,
            max_workers=args.max_workers,
        )

    if args.embed:
        embed_transcripts(db_conn)

    if args.detect:
        detect_contradictions(db_conn, nli_model=args.nli_model)

    if args.compile:
        compile_contradiction_montage(db_conn, top_n=args.top_n)

    if args.summary:
        summarize_contradictions(db_conn, args.summary)

    db_conn.close()
    logging.info("[i] Contradiction Clipper pipeline completed successfully.")

    if args.dashboard:
        dashboard.run_dashboard(DB_PATH)


if __name__ == "__main__":
    main()
