"""Tests for transformer module: task building, batch processing, CSV export."""

import tempfile
from pathlib import Path
import pytest
from src.processing.transformer import build_task, export_records_to_csv, process_records


def test_build_task():
    raw_item = {
        "text": "Bản tin thời sự tối nay tại Hà Nội",
        "videoMeta": {"duration": 120.0},
        "createTimeISO": "2026-09-01T12:00:00Z",
        "author": "vtv24news",
    }
    task = build_task(
        item=raw_item,
        clean_url="https://www.tiktok.com/@vtv24news/video/7391234567890",
        platform="tiktok",
        task_number=1,
        crawl_batch="WEEK3_0309",
        crawled_at="2026-09-03T10:00:00Z",
    )

    assert task["task_id"] == "ID_0001"
    assert task["item_id"] == "tt_7391234567890"
    assert task["platform"] == "tiktok"
    assert task["duration_formatted"] == "02:00"
    assert task["crawl_batch"] == "WEEK3_0309"
    assert task["platform_meta"]["author"] == "vtv24news"


def test_process_records():
    raw_items = [
        {
            "webVideoUrl": "https://www.tiktok.com/@user1/video/111111",
            "videoMeta": {"duration": 30.0},
            "text": "Tin tức nóng hổi",
        },
        {
            # Trùng URL trong cùng batch
            "webVideoUrl": "https://www.tiktok.com/@user1/video/111111?foo=bar",
            "videoMeta": {"duration": 30.0},
        },
        {
            # Trùng URL toàn cục (đã có từ tuần trước)
            "webVideoUrl": "https://www.tiktok.com/@user2/video/222222",
            "videoMeta": {"duration": 40.0},
        },
        {
            # URL hợp lệ mới
            "webVideoUrl": "https://www.tiktok.com/@user3/video/333333",
            "videoMeta": {"duration": 50.0},
        },
    ]

    global_index = {
        "urls": {
            "https://www.tiktok.com/@user2/video/222222": {"batch": "WEEK1_0109"}
        }
    }

    tasks, rejected = process_records(raw_items, "WEEK3_0309", global_index=global_index)

    assert len(tasks) == 2
    assert tasks[0]["platform_video_id"] == "111111"
    assert tasks[1]["platform_video_id"] == "333333"

    assert len(rejected) == 2
    reasons = [r["reason"] for r in rejected]
    assert "duplicate_url" in reasons
    assert "global_duplicate_url" in reasons


def test_export_records_to_csv():
    records = [
        {"task_id": "ID_0001", "url": "https://tiktok.com/1", "duration": 15},
        {"task_id": "ID_0002", "url": "https://tiktok.com/2", "duration": 25},
    ]
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / "output.csv"
        export_records_to_csv(records, csv_path)
        assert csv_path.is_file()
        content = csv_path.read_text(encoding="utf-8")
        assert "ID_0001" in content
        assert "ID_0002" in content
