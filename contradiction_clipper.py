"""Core pipeline for the Contradiction Clipper project."""
# pylint: disable=import-error, consider-using-f-string, broad-exception-caught

import argparse
import hashlib
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

DB_PATH = 'db/contradictions.db'


def init_db(conn):
    """Create required tables with UNIQUE constraints."""
    logging.info('[i] Initializing database schema.')
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
    logging.debug('[DEBUG] Hashing file %s', path)
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_video(url):
    """Download a video using yt-dlp and return the local path and video id."""
    logging.info('[i] Downloading video from %s', url)
    os.makedirs('videos/raw', exist_ok=True)
    vid_res = subprocess.run(
        ['yt-dlp', '--get-id', url],
        capture_output=True,
        text=True,
        check=False,
    )
    if vid_res.returncode != 0:
        logging.error('[x] Failed to get video id: %s', vid_res.stderr.strip())
        raise RuntimeError(vid_res.stderr.strip())
    video_id = vid_res.stdout.strip()
    logging.debug('[DEBUG] Video id %s resolved for %s', video_id, url)
    template = f'videos/raw/{video_id}.%(ext)s'
    res = subprocess.run(
        ['yt-dlp', '-f', 'best', '-o', template, url],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        logging.error('[x] Download failed: %s', res.stderr.strip())
        raise RuntimeError(res.stderr.strip())
    for ext in ['mp4', 'mkv', 'webm', 'flv', 'mov']:
        candidate = os.path.join('videos/raw', f'{video_id}.{ext}')
        if os.path.exists(candidate):
            logging.info('[i] Video downloaded to %s', candidate)
            return candidate, video_id
    logging.error('[x] Unable to locate downloaded file for %s', url)
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
                logging.info('[!] Already processed URL, skipping: %s', url)
                continue

            logging.info('[i] Downloading %s', url)
            path, vid = download_video(url)
            file_hash = hash_file(path)

            cursor.execute(
                'SELECT id FROM videos WHERE sha256=?', (file_hash,))
            if cursor.fetchone():
                logging.info(
                    '[!] Duplicate video content for %s; removing.', url
                )
                os.remove(path)
                continue

            cursor.execute(
                (
                    'INSERT INTO videos (url, video_id, file_path, sha256, '
                    'dl_timestamp) VALUES (?, ?, ?, ?, ?)'
                ),
                (url, vid, path, file_hash, datetime.utcnow().isoformat()),
            )
            conn.commit()
            logging.info('[i] Stored video %s', vid)
        except Exception as exc:
            logging.error('[x] Failed to process %s: %s', url, exc)

    conn.close()


def embed_transcripts(db_conn):
    """Generate embeddings for transcripts without existing embeddings."""
    logging.info('[i] Embedding transcripts.')
    cursor = db_conn.cursor()
    cursor.execute('SELECT id, text FROM transcripts')
    rows = cursor.fetchall()

    for tid, text in rows:
        cursor.execute(
            'SELECT 1 FROM embeddings WHERE transcript_id=?', (tid,))
        if cursor.fetchone():
            logging.info(
                '[!] Embedding exists for transcript %s, skipping.', tid
            )
            continue

        try:
            emb = hashlib.sha256(text.encode('utf-8')).hexdigest()
            cursor.execute(
                (
                    'INSERT INTO embeddings '
                    '(transcript_id, embedding, created_at) '
                    'VALUES (?, ?, ?)'
                ),
                (tid, emb.encode('utf-8'), datetime.utcnow().isoformat()),
            )
            db_conn.commit()
            logging.info('[i] Embedded transcript %s', tid)
        except Exception as exc:
            logging.error('[x] Failed to embed transcript %s: %s', tid, exc)


def _contradiction_score(text_a, text_b):
    logging.debug('[DEBUG] Scoring possible contradiction')
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
        for id_b, text_b in transcripts[i + 1:]:
            logging.debug('[DEBUG] Evaluating %s-%s', id_a, id_b)
            cursor.execute(
                (
                    'SELECT 1 FROM contradictions WHERE '
                    'segment_a_id=? AND segment_b_id=?'
                ),
                (id_a, id_b),
            )
            if cursor.fetchone():
                logging.info(
                    '[!] Contradiction already recorded for %s-%s, skipping.',
                    id_a,
                    id_b,
                )
                continue

            try:
                score = _contradiction_score(text_a, text_b)
                if score > 0:
                    cursor.execute(
                        (
                            'INSERT INTO contradictions '
                            '(segment_a_id, segment_b_id, confidence) '
                            'VALUES (?, ?, ?)'
                        ),
                        (id_a, id_b, score),
                    )
                    db_conn.commit()
                    logging.info(
                        '[i] Contradiction stored for %s-%s score=%s',
                        id_a,
                        id_b,
                        score,
                    )
            except Exception as exc:
                logging.error(
                    '[x] Failed to evaluate contradiction for %s-%s: %s',
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
                codec='libx264',
                audio_codec='aac',
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
    output_file='output/contradiction_montage.mp4',
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
    logging.info('[i] Compiling contradiction montage video.')
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

    for idx, (
        vid1,
        start1,
        _end1,
        vid2,
        start2,
        _end2,
        _conf,
    ) in enumerate(contradictions):
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
        logging.warning('[!] No clips extracted. Exiting compilation.')
        return

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        output_file,
        codec='libx264',
        audio_codec='aac',
    )

    logging.info(
        '[i] Contradiction montage successfully created: %s', output_file
    )


def main():
    """Entry point for the CLI utility."""
    logging.info('[i] Starting Contradiction Clipper pipeline.')
    parser = argparse.ArgumentParser(
        description='Contradiction Clipper - Complete Pipeline'
    )
    parser.add_argument(
        '--video_list',
        help='Path to file containing YouTube video URLs (one per line)'
    )
    parser.add_argument(
        '--embed',
        action='store_true',
        help='Generate embeddings for transcripts.'
    )
    parser.add_argument(
        '--detect',
        action='store_true',
        help='Detect contradictions in transcripts.'
    )
    parser.add_argument(
        '--compile',
        action='store_true',
        help='Compile detected contradictions into video.'
    )
    parser.add_argument(
        '--top_n',
        type=int,
        default=20,
        help='Number of contradictions to include in the montage.'
    )

    args = parser.parse_args()

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db_conn = sqlite3.connect(DB_PATH)
    init_db(db_conn)

    if args.video_list:
        if not os.path.exists(args.video_list):
            logging.error(
                '[x] URL list file does not exist: %s', args.video_list)
            sys.exit(1)
        process_videos(args.video_list)

    if args.embed:
        embed_transcripts(db_conn)

    if args.detect:
        detect_contradictions(db_conn)

    if args.compile:
        compile_contradiction_montage(db_conn, top_n=args.top_n)

    db_conn.close()
    logging.info("[i] Contradiction Clipper pipeline completed successfully.")


if __name__ == "__main__":
    main()
