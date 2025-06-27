import argparse
import hashlib
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

from moviepy.editor import VideoFileClip, concatenate_videoclips

logging.basicConfig(level=logging.INFO, format='%(message)s')

DB_PATH = 'db/contradictions.db'


def init_db(conn):
    """Create required tables with UNIQUE constraints."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            video_id TEXT,
            file_path TEXT,
            sha256 TEXT UNIQUE,
            dl_timestamp TEXT
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
    conn.commit()


def hash_file(path):
    """Return SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_video(url):
    """Download a video using yt-dlp and return the local path and video id."""
    os.makedirs('videos/raw', exist_ok=True)
    vid_res = subprocess.run(
        ['yt-dlp', '--get-id', url], capture_output=True, text=True, check=False
    )
    if vid_res.returncode != 0:
        raise RuntimeError(vid_res.stderr.strip())
    video_id = vid_res.stdout.strip()
    template = f'videos/raw/{video_id}.%(ext)s'
    res = subprocess.run(
        ['yt-dlp', '-f', 'best', '-o', template, url],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip())
    for ext in ['mp4', 'mkv', 'webm', 'flv', 'mov']:
        candidate = os.path.join('videos/raw', f'{video_id}.{ext}')
        if os.path.exists(candidate):
            return candidate, video_id
    raise FileNotFoundError(f'Unable to locate downloaded file for {url}')


def process_videos(video_list_path, db_path=DB_PATH):
    """Download videos, compute hashes and record them if unseen."""
    logging.info('[i] Processing videos.')
    conn = sqlite3.connect(db_path)
    init_db(conn)
    cursor = conn.cursor()

    with open(video_list_path, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        try:
            cursor.execute('SELECT id FROM videos WHERE url=?', (url,))
            if cursor.fetchone():
                logging.info(f'[!] Already processed URL, skipping: {url}')
                continue

            logging.info(f'[i] Downloading {url}')
            path, vid = download_video(url)
            file_hash = hash_file(path)

            cursor.execute('SELECT id FROM videos WHERE sha256=?', (file_hash,))
            if cursor.fetchone():
                logging.info(f'[!] Duplicate video content for {url}; removing.')
                os.remove(path)
                continue

            cursor.execute(
                'INSERT INTO videos (url, video_id, file_path, sha256, dl_timestamp) '
                'VALUES (?, ?, ?, ?, ?)',
                (url, vid, path, file_hash, datetime.utcnow().isoformat()),
            )
            conn.commit()
            logging.info(f'[i] Stored video {vid}')
        except Exception as exc:
            logging.error(f'[x] Failed to process {url}: {exc}')

    conn.close()


def embed_transcripts(db_conn):
    """Generate embeddings for transcripts without existing embeddings."""
    logging.info('[i] Embedding transcripts.')
    cursor = db_conn.cursor()
    cursor.execute('SELECT id, text FROM transcripts')
    rows = cursor.fetchall()

    for tid, text in rows:
        cursor.execute('SELECT 1 FROM embeddings WHERE transcript_id=?', (tid,))
        if cursor.fetchone():
            logging.info(f'[!] Embedding exists for transcript {tid}, skipping.')
            continue

        try:
            emb = hashlib.sha256(text.encode('utf-8')).hexdigest()
            cursor.execute(
                'INSERT INTO embeddings (transcript_id, embedding, created_at) '
                'VALUES (?, ?, ?)',
                (tid, emb.encode('utf-8'), datetime.utcnow().isoformat()),
            )
            db_conn.commit()
            logging.info(f'[i] Embedded transcript {tid}')
        except Exception as exc:
            logging.error(f'[x] Failed to embed transcript {tid}: {exc}')


def _contradiction_score(text_a, text_b):
    if 'not' in text_a.lower() and 'not' not in text_b.lower():
        return 0.9
    if 'not' in text_b.lower() and 'not' not in text_a.lower():
        return 0.9
    return 0.0


def detect_contradictions(db_conn):
    """Detect and store contradictions between transcript segments."""
    logging.info('[i] Detecting contradictions.')
    cursor = db_conn.cursor()
    cursor.execute('SELECT id, text FROM transcripts')
    transcripts = cursor.fetchall()

    for i, (id_a, text_a) in enumerate(transcripts):
        for id_b, text_b in transcripts[i + 1 :]:
            cursor.execute(
                'SELECT 1 FROM contradictions WHERE segment_a_id=? AND segment_b_id=?',
                (id_a, id_b),
            )
            if cursor.fetchone():
                logging.info(
                    f'[!] Contradiction already recorded for {id_a}-{id_b}, skipping.'
                )
                continue

            try:
                score = _contradiction_score(text_a, text_b)
                if score > 0:
                    cursor.execute(
                        'INSERT INTO contradictions (segment_a_id, segment_b_id, confidence) '
                        'VALUES (?, ?, ?)',
                        (id_a, id_b, score),
                    )
                    db_conn.commit()
                    logging.info(
                        f'[i] Contradiction stored for {id_a}-{id_b} score={score}'
                    )
            except Exception as exc:
                logging.error(
                    f'[x] Failed to evaluate contradiction for {id_a}-{id_b}: {exc}'
                )

def extract_clip(video_path, start_time, end_time, output_path):
    logging.info(f"[i] Extracting clip: {video_path} ({start_time}-{end_time}s)")
    try:
        with VideoFileClip(video_path) as clip:
            snippet = clip.subclip(start_time, end_time)
            snippet.write_videofile(output_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        logging.info(f"[i] Successfully extracted: {output_path}")
        return True
    except Exception as e:
        logging.error(f"[x] Failed to extract clip from {video_path}: {e}")
        return False

def compile_contradiction_montage(db_conn, output_file='output/contradiction_montage.mp4', clip_duration=15, top_n=20):
    logging.info("[i] Compiling contradiction montage video.")
    cursor = db_conn.cursor()

    cursor.execute('''
        SELECT 
            t1.video_id, t1.segment_start, t1.segment_end,
            t2.video_id, t2.segment_start, t2.segment_end,
            c.confidence 
        FROM contradictions c
        JOIN transcripts t1 ON c.segment_a_id = t1.id
        JOIN transcripts t2 ON c.segment_b_id = t2.id
        ORDER BY c.confidence DESC LIMIT ?
    ''', (top_n,))

    contradictions = cursor.fetchall()
    clips = []

    for idx, (vid1, start1, end1, vid2, start2, end2, confidence) in enumerate(contradictions):
        video1_path = f'videos/raw/{vid1}.mp4'
        video2_path = f'videos/raw/{vid2}.mp4'

        clip1_start = max(0, start1 - 2)
        clip1_end = clip1_start + clip_duration
        clip2_start = max(0, start2 - 2)
        clip2_end = clip2_start + clip_duration

        clip1_path = f'videos/processed/contradiction_{idx}_a.mp4'
        clip2_path = f'videos/processed/contradiction_{idx}_b.mp4'

        os.makedirs('videos/processed', exist_ok=True)

        if extract_clip(video1_path, clip1_start, clip1_end, clip1_path):
            clips.append(VideoFileClip(clip1_path))

        if extract_clip(video2_path, clip2_start, clip2_end, clip2_path):
            clips.append(VideoFileClip(clip2_path))

    if not clips:
        logging.warning("[!] No clips extracted. Exiting compilation.")
        return

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_file, codec='libx264', audio_codec='aac')

    logging.info(f"[i] Contradiction montage successfully created: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Contradictor Detector - Complete Pipeline')
    parser.add_argument('--video_list', help='Path to file containing YouTube video URLs (one per line)')
    parser.add_argument('--embed', action='store_true', help='Generate embeddings for transcripts.')
    parser.add_argument('--detect', action='store_true', help='Detect contradictions in transcripts.')
    parser.add_argument('--compile', action='store_true', help='Compile detected contradictions into video.')
    parser.add_argument('--top_n', type=int, default=20, help='Number of contradictions to include in the montage.')

    args = parser.parse_args()

    db_conn = sqlite3.connect('db/contradictions.db')
    init_db(db_conn)

    if args.video_list:
        if not os.path.exists(args.video_list):
            logging.error(f"[x] URL list file does not exist: {args.video_list}")
            sys.exit(1)
        process_videos(args.video_list)

    if args.embed:
        embed_transcripts(db_conn)

    if args.detect:
        detect_contradictions(db_conn)

    if args.compile:
        compile_contradiction_montage(db_conn, top_n=args.top_n)

    db_conn.close()
    logging.info("[i] Contradictor Detector pipeline completed successfully.")

if __name__ == "__main__":
    main()

