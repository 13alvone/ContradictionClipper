from moviepy.editor import VideoFileClip, concatenate_videoclips

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

