import os
import sqlite3
import tempfile
from unittest import mock
import sys
from pathlib import Path

# Ensure repository root is on the module path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub moviepy to avoid heavy dependency during tests
sys.modules['moviepy'] = mock.Mock()
sys.modules['moviepy.editor'] = mock.Mock()

import pytest

import contradiction_clipper as cc


def fake_download(url):
    video_id = url.split('/')[-1]
    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, f'{video_id}.mp4')
    with open(path, 'wb') as f:
        f.write(url.encode())
    return path, video_id


def setup_db(tmp_path):
    db_path = tmp_path / 'test.db'
    conn = sqlite3.connect(db_path)
    cc.init_db(conn)
    return conn, str(db_path)


def test_process_videos_dedup(tmp_path):
    conn, db_path = setup_db(tmp_path)
    urls = ['http://example.com/video1']
    list_file = tmp_path / 'urls.txt'
    list_file.write_text('\n'.join(urls))
    with mock.patch('contradiction_clipper.download_video', side_effect=fake_download) as mock_dl:
        cc.process_videos(str(list_file), db_path)
        cc.process_videos(str(list_file), db_path)
        assert mock_dl.call_count == 1
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM videos')
    count = cursor.fetchone()[0]
    assert count == 1
    conn.close()


def test_embed_transcripts_unique(tmp_path):
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transcripts(video_id, text) VALUES('vid', 'foo')")
    tid = cursor.lastrowid
    conn.commit()
    cc.embed_transcripts(conn)
    cc.embed_transcripts(conn)
    cursor.execute('SELECT COUNT(*) FROM embeddings WHERE transcript_id=?', (tid,))
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_detect_contradictions_unique(tmp_path):
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transcripts(video_id, text) VALUES('vid', 'not true')")
    a = cursor.lastrowid
    cursor.execute("INSERT INTO transcripts(video_id, text) VALUES('vid', 'true')")
    b = cursor.lastrowid
    conn.commit()
    cc.detect_contradictions(conn)
    cc.detect_contradictions(conn)
    cursor.execute('SELECT COUNT(*) FROM contradictions')
    assert cursor.fetchone()[0] == 1
    conn.close()
