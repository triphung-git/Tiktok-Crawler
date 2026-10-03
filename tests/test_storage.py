"""Tests for storage module: atomic write, JSON index management, SQLite database."""

import json
import tempfile
from pathlib import Path
import pytest
from src.storage.database import Database
from src.storage.json_storage import (
    GlobalIndexManager,
    MetadataManager,
    atomic_write_json,
    load_json,
)


def test_atomic_write_and_load_json():
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_file = Path(tmp_dir) / "test.json"
        data = {"hello": "world", "number": 123, "list": [1, 2, 3]}

        atomic_write_json(json_file, data)
        assert json_file.is_file()

        loaded = load_json(json_file)
        assert loaded == data

        # Non-existent file returns default
        missing = load_json(Path(tmp_dir) / "missing.json", default={"default": True})
        assert missing == {"default": True}


def test_global_index_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_file = Path(tmp_dir) / "processed_index.json"
        mgr = GlobalIndexManager(index_path=index_file)

        initial = mgr.load()
        assert initial["total_records"] == 0
        assert not mgr.has_url("https://tiktok.com/@u/video/1")

        new_tasks = [
            {"task_id": "ID_0001", "item_id": "tt_1", "original_url": "https://tiktok.com/@u/video/1"},
            {"task_id": "ID_0002", "item_id": "tt_2", "original_url": "https://tiktok.com/@u/video/2"},
        ]
        mgr.update_with_tasks(new_tasks, "WEEK3_0309")

        assert mgr.has_url("https://tiktok.com/@u/video/1")
        assert mgr.has_url("https://tiktok.com/@u/video/2")
        assert not mgr.has_url("https://tiktok.com/@u/video/3")

        # Reload from disk
        mgr2 = GlobalIndexManager(index_path=index_file)
        loaded = mgr2.load()
        assert loaded["total_records"] == 2


def test_metadata_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        meta_file = Path(tmp_dir) / "metadata.json"
        mgr = MetadataManager(meta_file)

        mgr.update_record({"item_id": "tt_101", "task_id": "ID_0001", "duration": 12.5})
        mgr.update_record({"item_id": "tt_102", "task_id": "ID_0002", "duration": 18.0})
        mgr.flush()

        assert meta_file.is_file()
        with open(meta_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        assert len(records) == 2
        assert records[0]["item_id"] == "tt_101"


def test_sqlite_database():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test.db"
        db = Database(db_path=db_file)

        task = {
            "task_id": "ID_0001",
            "item_id": "tt_111",
            "platform": "tiktok",
            "original_url": "https://tiktok.com/@u/video/111",
            "title": "Sample Video",
            "duration_seconds": 35.5,
            "crawl_batch": "WEEK3_0309",
            "crawled_at": "2026-09-03T12:00:00Z",
            "status": "pending",
        }
        db.insert_task(task)
        assert db.has_url("https://tiktok.com/@u/video/111") is True
        assert db.has_url("https://tiktok.com/@u/video/222") is False

        # Update status
        db.update_task_status("ID_0001", "success", audio_path="audio/ID_0001.wav")
        batch_tasks = db.get_batch_tasks("WEEK3_0309")
        assert len(batch_tasks) == 1
        assert batch_tasks[0]["status"] == "success"
        assert batch_tasks[0]["audio_path"] == "audio/ID_0001.wav"

        # Save segments
        segments = [
            {"filename": "ID_0001_seg001.wav", "duration": 4.5, "start": 0.0, "end": 4.5},
            {"filename": "ID_0001_seg002.wav", "duration": 6.2, "start": 5.0, "end": 11.2},
        ]
        db.save_segments("ID_0001", segments)
