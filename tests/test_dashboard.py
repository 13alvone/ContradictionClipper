"""Tests for the dashboard Flask app."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard  # noqa: E402


def test_dashboard_routes(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE files(sha256 TEXT PRIMARY KEY, video_id TEXT, file_path TEXT, size_bytes INTEGER, hash_ts TEXT)"
    )
    conn.execute(
        "CREATE TABLE videos(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, file_hash TEXT, dl_timestamp TEXT)"
    )
    conn.commit()
    conn.close()

    app = dashboard.create_app(str(db))
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/videos").status_code == 200

