"""Unit tests for hashing and DB uniqueness."""
# pylint: disable=wrong-import-position

import hashlib
import sqlite3
import sys
import types
from pathlib import Path

import pytest

# Ensure repository root is on the module path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide dummy moviepy modules so the import in contradiction_clipper does not
# require the actual dependency during tests.
sys.modules.setdefault("moviepy", types.ModuleType("moviepy"))
sys.modules.setdefault("moviepy.editor", types.ModuleType("moviepy.editor"))

import contradiction_clipper as cc  # noqa: E402
# pylint: disable=wrong-import-position


def test_hash_file_consistency(tmp_path):
    """Ensure hashing the same file yields consistent output."""
    sample = b"sample video data"
    file_path = tmp_path / "sample.mp4"
    file_path.write_bytes(sample)
    first = cc.hash_file(file_path)
    second = cc.hash_file(file_path)
    expected = hashlib.sha256(sample).hexdigest()
    assert first == second == expected


def test_unique_url_constraint(tmp_path):
    """Verify UNIQUE constraint prevents duplicate URLs."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    cc.init_db(conn)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (sha256, video_id, file_path, size_bytes, hash_ts) "
        "VALUES (?, ?, ?, ?, ?)",
        ("hash1", "a", "/tmp/a.mp4", 1, "now"),
    )
    cursor.execute(
        "INSERT INTO videos (url, file_hash, dl_timestamp) VALUES (?, ?, ?)",
        ("http://example.com/a", "hash1", "now"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            "INSERT INTO videos (url, file_hash, dl_timestamp) VALUES (?, ?, ?)",
            ("http://example.com/a", "hash2", "now"),
        )
        conn.commit()
    conn.close()


def test_schema_version_recorded(tmp_path):
    """Schema version table should be initialized."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    cc.init_db(conn)
    assert cc.get_schema_version(conn) == cc.SCHEMA_VERSION
    conn.close()
