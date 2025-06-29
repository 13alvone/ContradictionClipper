"""Integration tests for the Contradiction Clipper pipeline."""
# pylint: disable=wrong-import-position

import os
import sqlite3
import tempfile
from unittest import mock
import sys
from pathlib import Path
import subprocess
import logging
import numpy as np

# Ensure repository root is on the module path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import contradiction_clipper as cc  # noqa: E402

# pylint: disable=wrong-import-position


def fake_download(url):
    """Create a fake video file for offline tests."""
    video_id = url.split("/")[-1]
    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, f"{video_id}.mp4")
    with open(path, "wb") as f:
        f.write(url.encode())
    return path, video_id


def setup_db(tmp_path):
    """Initialize a temporary database for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    cc.init_db(conn)
    assert cc.get_schema_version(conn) == cc.SCHEMA_VERSION
    return conn, str(db_path)


def test_process_videos_dedup(tmp_path):
    """Videos with duplicate URLs should be processed once."""
    conn, db_path = setup_db(tmp_path)
    urls = ["http://example.com/video1"]
    list_file = tmp_path / "urls.txt"
    list_file.write_text("\n".join(urls))
    with mock.patch(
        "contradiction_clipper.download_video", side_effect=fake_download
    ) as mock_dl:
        cc.process_videos(str(list_file), db_path)
        cc.process_videos(str(list_file), db_path)
        assert mock_dl.call_count == 1
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    count = cursor.fetchone()[0]
    assert count == 1
    conn.close()


def test_process_videos_parallel_dedup(tmp_path):
    """Parallel processing should not duplicate URLs."""
    conn, db_path = setup_db(tmp_path)
    urls = ["http://example.com/video1", "http://example.com/video1"]
    list_file = tmp_path / "urls.txt"
    list_file.write_text("\n".join(urls))
    with mock.patch(
        "contradiction_clipper.download_video", side_effect=fake_download
    ) as mock_dl:
        cc.process_videos(str(list_file), db_path, max_workers=2)
        assert mock_dl.call_count == 1
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_embed_transcripts_unique(tmp_path):
    """Ensure embeddings are created only once per transcript."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transcripts(video_id, text) VALUES('vid', 'foo')"
    )
    tid = cursor.lastrowid
    conn.commit()
    def fake_loader(_name="all-MiniLM-L6-v2"):
        class Dummy:
            def encode(self, text, show_progress_bar=False):
                return np.array([0.1, 0.2, 0.3], dtype=np.float32)

        return Dummy()

    with mock.patch("contradiction_clipper.load_embedding_model", fake_loader):
        cc.embed_transcripts(conn)
        cc.embed_transcripts(conn)
    cursor.execute(
        "SELECT embedding FROM embeddings WHERE transcript_id=?", (tid,)
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert isinstance(rows[0][0], bytes)
    conn.close()


def test_detect_contradictions_unique(tmp_path):
    """Detecting twice should not duplicate contradictions."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transcripts(video_id, text) VALUES('vid', 'not true')"
    )
    cursor.execute(
        "INSERT INTO transcripts(video_id, text) VALUES('vid', 'true')"
    )
    conn.commit()

    def fake_loader(_model):
        return lambda a, b: 0.8

    with mock.patch("contradiction_clipper.load_nli_model", fake_loader):
        cc.detect_contradictions(conn)
        cc.detect_contradictions(conn)

    cursor.execute("SELECT COUNT(*) FROM contradictions")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_transcribe_videos_once(tmp_path, monkeypatch):
    """Transcribing should only occur once per video."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    video_path = tmp_path / "v1.mp4"
    video_path.write_bytes(b"data")
    cursor.execute(
        "INSERT INTO files(sha256, video_id, file_path, size_bytes, hash_ts)"
        " VALUES(?,?,?,?,?)",
        ("hash", "v1", str(video_path), 4, "now"),
    )
    cursor.execute(
        "INSERT INTO videos(url, file_hash, dl_timestamp)" " VALUES(?,?,?)",
        ("http://x/v1", "hash", "now"),
    )
    conn.commit()

    def fake_run(cmd, capture_output=True, text=True, check=False):
        out_dir = tmp_path / "transcripts"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "v1.json"
        out_file.write_text(
            '{"segments": [{"start": 0, "end": 1, "text": "hi"}]}'
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.chdir(tmp_path)
    whisper_bin = tmp_path / "whisper"
    whisper_bin.write_text("echo stub")
    whisper_bin.chmod(0o755)
    model_file = tmp_path / "models" / "ggml-base.en.bin"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_text("model")
    with mock.patch(
        "contradiction_clipper.subprocess.run", side_effect=fake_run
    ) as mock_run:
        cc.transcribe_videos(conn, whisper_bin=str(whisper_bin))
        cc.transcribe_videos(conn, whisper_bin=str(whisper_bin))
        assert mock_run.call_count == 1

    cursor.execute("SELECT COUNT(*) FROM transcripts WHERE video_id='v1'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_transcribe_parallel_once(tmp_path, monkeypatch):
    """Parallel transcription should only occur once per video."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    video_path = tmp_path / "v2.mp4"
    video_path.write_bytes(b"data")
    cursor.execute(
        "INSERT INTO files(sha256, video_id, file_path, size_bytes, hash_ts)"
        " VALUES(?,?,?,?,?)",
        ("hash2", "v2", str(video_path), 4, "now"),
    )
    cursor.execute(
        "INSERT INTO videos(url, file_hash, dl_timestamp)" " VALUES(?,?,?)",
        ("http://x/v2", "hash2", "now"),
    )
    conn.commit()

    def fake_run(cmd, capture_output=True, text=True, check=False):
        out_dir = tmp_path / "transcripts"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "v2.json"
        out_file.write_text(
            '{"segments": [{"start": 0, "end": 1, "text": "hi"}]}'
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.chdir(tmp_path)
    whisper_bin = tmp_path / "whisper"
    whisper_bin.write_text("echo stub")
    whisper_bin.chmod(0o755)
    model_file = tmp_path / "models" / "ggml-base.en.bin"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_text("model")
    with mock.patch(
        "contradiction_clipper.subprocess.run", side_effect=fake_run
    ) as mock_run:
        cc.transcribe_videos(conn, whisper_bin=str(whisper_bin), max_workers=2)
        cc.transcribe_videos(conn, whisper_bin=str(whisper_bin), max_workers=2)
        assert mock_run.call_count == 1

    cursor.execute("SELECT COUNT(*) FROM transcripts WHERE video_id='v2'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_summarize_contradictions_unique(tmp_path):
    """Summary file should contain each contradiction pair only once."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transcripts(video_id, segment_start, segment_end, text)"
        " VALUES('v1', 0, 1, 'no')"
    )
    cursor.execute(
        "INSERT INTO transcripts(video_id, segment_start, segment_end, text)"
        " VALUES('v1', 2, 3, 'yes')"
    )
    conn.commit()

    def fake_loader(_model):
        return lambda a, b: 0.9

    with mock.patch("contradiction_clipper.load_nli_model", fake_loader):
        cc.detect_contradictions(conn)

    summary = tmp_path / "out.txt"
    cc.summarize_contradictions(conn, str(summary))

    lines = summary.read_text().strip().splitlines()
    assert len(lines) == 1
    conn.close()


def test_process_videos_duplicate_files(tmp_path):
    """Duplicate file hashes should not leave extra files on disk."""
    conn, db_path = setup_db(tmp_path)
    urls = ["http://x/v1", "http://x/v2"]
    list_file = tmp_path / "urls.txt"
    list_file.write_text("\n".join(urls))

    def fake_dl(url):
        vid = "same"
        path = tmp_path / f"{vid}_{url.split('/')[-1]}.mp4"
        path.write_bytes(b"data")
        return str(path), vid

    with mock.patch(
        "contradiction_clipper.download_video", side_effect=fake_dl
    ):
        cc.process_videos(str(list_file), db_path, max_workers=1)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM videos")
    assert cursor.fetchone()[0] == 2
    assert not (tmp_path / "same_v2.mp4").exists()
    conn.close()


def test_auto_install_whisper(tmp_path, monkeypatch):
    """transcribe_videos should run install_whisper.sh when binary missing."""
    conn, _ = setup_db(tmp_path)
    cursor = conn.cursor()
    video_path = tmp_path / "v3.mp4"
    video_path.write_bytes(b"data")
    cursor.execute(
        "INSERT INTO files(sha256, video_id, file_path, size_bytes, hash_ts)"
        " VALUES(?,?,?,?,?)",
        ("hash3", "v3", str(video_path), 4, "now"),
    )
    cursor.execute(
        "INSERT INTO videos(url, file_hash, dl_timestamp) VALUES(?,?,?)",
        ("http://x/v3", "hash3", "now"),
    )
    conn.commit()

    install_script = tmp_path / "install_whisper.sh"
    install_script.write_text("#!/bin/bash\ntouch whisper\nmkdir -p models\ntouch models/ggml-base.en.bin\n")
    install_script.chmod(0o755)

    monkeypatch.chdir(tmp_path)
    with monkeypatch.context() as m:
        def fake_run(cmd, capture_output=True, text=True):
            assert cmd[0].endswith("install_whisper.sh")
            subprocess.run([install_script])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        m.setattr(cc, "subprocess", mock.Mock(run=fake_run))
        cc.ensure_whisper_installed(str(tmp_path / "whisper"))

    assert (tmp_path / "whisper").exists()
    assert (tmp_path / "models" / "ggml-base.en.bin").exists()
    conn.close()


def test_install_whisper_failure(tmp_path, monkeypatch, caplog):
    """ensure_whisper_installed returns False when script fails."""
    fail_script = tmp_path / "install_whisper.sh"
    fail_script.write_text("#!/bin/bash\necho fail >&2\nexit 1\n")
    fail_script.chmod(0o755)

    monkeypatch.setattr(cc.os.path, "dirname", lambda _p: str(tmp_path))
    caplog.set_level(logging.INFO)
    ok = cc.ensure_whisper_installed(str(tmp_path / "whisper"))

    assert not ok
    assert any("install_whisper.sh failed" in r.message for r in caplog.records)
