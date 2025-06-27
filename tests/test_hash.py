import hashlib
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure repository root is on the module path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub moviepy to allow offline testing
sys.modules['moviepy'] = mock.Mock()
sys.modules['moviepy.editor'] = mock.Mock()

import contradiction_clipper as cc


def test_hash_file_consistency(tmp_path):
    sample = b'sample video data'
    file_path = tmp_path / 'sample.mp4'
    file_path.write_bytes(sample)
    first = cc.hash_file(file_path)
    second = cc.hash_file(file_path)
    expected = hashlib.sha256(sample).hexdigest()
    assert first == second == expected


def test_unique_url_constraint(tmp_path):
    db = tmp_path / 'test.db'
    conn = sqlite3.connect(db)
    cc.init_db(conn)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO videos (url, video_id, file_path, sha256, dl_timestamp) '
        'VALUES (?, ?, ?, ?, ?)',
        ('http://example.com/a', 'a', '/tmp/a.mp4', 'hash1', 'now'),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            'INSERT INTO videos (url, video_id, file_path, sha256, dl_timestamp) '
            'VALUES (?, ?, ?, ?, ?)',
            ('http://example.com/a', 'b', '/tmp/b.mp4', 'hash2', 'now'),
        )
        conn.commit()
    conn.close()
