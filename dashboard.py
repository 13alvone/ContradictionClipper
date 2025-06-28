import os
import sqlite3
import logging
from flask import Flask, render_template_string, send_from_directory

DB_PATH = 'db/contradictions.db'


def create_app(db_path=DB_PATH):
    """Return a Flask app connected to the specified SQLite database."""
    app = Flask(__name__)

    def query(sql, args=()):
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, args)
            return cur.fetchall()

    @app.route('/')
    def index():
        return render_template_string(
            """
            <h1>Contradiction Clipper Dashboard</h1>
            <ul>
              <li><a href='/videos'>Videos</a></li>
              <li><a href='/transcripts'>Transcripts</a></li>
              <li><a href='/contradictions'>Contradictions</a></li>
            </ul>
            """
        )

    @app.route('/video/<vid>')
    def video_file(vid):
        for ext in ['mp4', 'mkv', 'webm', 'flv', 'mov']:
            path = os.path.join('videos/raw', f'{vid}.{ext}')
            if os.path.exists(path):
                return send_from_directory('videos/raw', f'{vid}.{ext}')
        return 'Not found', 404

    @app.route('/videos')
    def list_videos():
        rows = query(
            'SELECT f.video_id AS video_id, v.url AS url '
            'FROM videos v JOIN files f ON v.file_hash = f.sha256'
        )
        html = ['<h1>Videos</h1>']
        for row in rows:
            html.append(
                f"<div><p>{row['url']}</p>"
                f"<video width='320' controls src='/video/{row['video_id']}'></video>"  # pylint: disable=line-too-long
                '</div>'
            )
        return '\n'.join(html)

    @app.route('/transcripts')
    def list_transcripts():
        rows = query(
            'SELECT video_id, segment_start, segment_end, text FROM transcripts'
        )
        html = ['<h1>Transcripts</h1>']
        for row in rows:
            html.append(
                f"<div><p>{row['text']}</p>"
                f"<video width='320' controls src='/video/{row['video_id']}#t={row['segment_start']},{row['segment_end']}'></video>"  # pylint: disable=line-too-long
                '</div>'
            )
        return '\n'.join(html)

    @app.route('/contradictions')
    def list_contradictions():
        rows = query(
            '''
            SELECT c.confidence,
                   t1.video_id AS vid1, t1.segment_start AS s1, t1.segment_end AS e1, t1.text AS text1,
                   t2.video_id AS vid2, t2.segment_start AS s2, t2.segment_end AS e2, t2.text AS text2
            FROM contradictions c
            JOIN transcripts t1 ON c.segment_a_id = t1.id
            JOIN transcripts t2 ON c.segment_b_id = t2.id
            ORDER BY c.confidence DESC
            '''
        )
        html = ['<h1>Contradictions</h1>']
        for row in rows:
            html.extend([
                '<div style="margin-bottom:20px;">',
                f"<p>Confidence: {row['confidence']:.2f}</p>",
                f"<p>{row['text1']}</p>",
                f"<video width='320' controls src='/video/{row['vid1']}#t={row['s1']},{row['e1']}'></video>",
                f"<p>{row['text2']}</p>",
                f"<video width='320' controls src='/video/{row['vid2']}#t={row['s2']},{row['e2']}'></video>",
                '</div>'
            ])
        return '\n'.join(html)

    return app


def run_dashboard(db_path=DB_PATH, host='127.0.0.1', port=5000):
    """Launch the Flask dashboard."""
    logging.info('[i] Starting dashboard on %s:%s', host, port)
    create_app(db_path).run(host=host, port=port)
