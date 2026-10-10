"""Database & Data Integrity Testing with SQL.

Verifies database schema constraints, data consistency, foreign keys,
and indexing performance for the TikTok Pipeline SQLite Database.
"""

import sqlite3
import pytest
from pathlib import Path
from src.storage.database import Database


@pytest.fixture
def test_db(tmp_path: Path):
    """Fixture providing a temporary SQLite database with test schema."""
    db_file = tmp_path / "test_pipeline.db"
    db = Database(db_path=db_file)
    return db


def test_sql_uniqueness_constraint_in_global_index(test_db: Database):
    """TC-DB-01: Ensure global_index table enforces URL uniqueness."""
    url = "https://www.tiktok.com/@vtv24/video/7123456789012345678"
    
    # Insert first record via insert_task
    test_db.insert_task({
        "task_id": "TASK_001",
        "item_id": "7123456789012345678",
        "original_url": url,
        "crawl_batch": "WEEK1_0109",
        "crawled_at": "2026-10-10T12:00:00Z"
    })
    
    # Try inserting duplicate URL with different task_id in another batch
    test_db.insert_task({
        "task_id": "TASK_002",
        "item_id": "7123456789012345678",
        "original_url": url,
        "crawl_batch": "WEEK2_0209",
        "crawled_at": "2026-10-10T14:00:00Z"
    })
    
    # Query database using raw SQL to verify there is strictly 1 record for this URL
    with test_db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM global_index WHERE url = ?", (url,))
        count = cursor.fetchone()[0]
        assert count == 1, "Duplicate URLs must not exist in global_index"


def test_sql_not_null_constraints(test_db: Database):
    """TC-DB-05: Ensure videos table has no NULL values on mandatory fields."""
    sample_tasks = [
        {
            "task_id": "TASK_001",
            "item_id": "ITEM_001",
            "platform": "tiktok",
            "original_url": "https://www.tiktok.com/@vtv24/video/7001",
            "title": "Bản tin thời sự",
            "duration_seconds": 45.5,
            "language_region": "northern",
            "crawl_batch": "WEEK3_0309",
            "status": "completed",
        },
        {
            "task_id": "TASK_002",
            "item_id": "ITEM_002",
            "platform": "tiktok",
            "original_url": "https://www.tiktok.com/@user2/video/7002",
            "title": "Ẩm thực miền Tây",
            "duration_seconds": 60.0,
            "language_region": "southern",
            "crawl_batch": "WEEK3_0309",
            "status": "pending",
        }
    ]
    for t in sample_tasks:
        test_db.insert_task(t)

    with test_db._connection() as conn:
        cursor = conn.cursor()
        # SQL assertion: check for any violating records
        cursor.execute("""
            SELECT COUNT(*) FROM videos 
            WHERE task_id IS NULL 
               OR original_url IS NULL 
               OR status IS NULL 
               OR crawl_batch IS NULL
        """)
        null_count = cursor.fetchone()[0]
        assert null_count == 0, "Mandatory columns must not contain NULL values"


def test_sql_referential_integrity_foreign_key(test_db: Database):
    """TC-DB-03: Ensure segments are properly linked to valid parent tasks (No orphan segments)."""
    # Insert parent task
    test_db.insert_task({
        "task_id": "PARENT_TASK_001",
        "original_url": "https://www.tiktok.com/@vtv24/video/7001",
        "title": "Video thời sự",
        "duration_seconds": 30.0,
        "crawl_batch": "WEEK3_0309",
    })

    # Insert segments via save_segments
    test_db.save_segments("PARENT_TASK_001", [
        {"filename": "seg_001.wav", "duration": 5.2, "start": 0.0, "end": 5.2, "filepath": "/data/seg_001.wav"},
        {"filename": "seg_002.wav", "duration": 8.4, "start": 5.2, "end": 13.6, "filepath": "/data/seg_002.wav"},
    ])

    with test_db._connection() as conn:
        cursor = conn.cursor()
        # SQL query finding orphan segments without existing parent in videos table
        cursor.execute("""
            SELECT s.id, s.task_id 
            FROM segments s 
            LEFT JOIN videos v ON s.task_id = v.task_id 
            WHERE v.task_id IS NULL
        """)
        orphan_records = cursor.fetchall()
        assert len(orphan_records) == 0, f"Found orphan segments without parent video: {orphan_records}"


def test_sql_business_logic_audio_duration_bounds(test_db: Database):
    """TC-DB-04: Validate business rule: audio segments must be between 2.0s and 15.0s."""
    test_db.insert_task({
        "task_id": "TASK_ASR_BOUNDS",
        "original_url": "https://www.tiktok.com/@user/video/7003",
        "crawl_batch": "WEEK3_0309",
    })
    
    # Valid segments
    test_db.save_segments("TASK_ASR_BOUNDS", [
        {"filename": "seg_valid_1.wav", "duration": 3.5, "start": 0.0, "end": 3.5, "filepath": "/data/1.wav"},
        {"filename": "seg_valid_2.wav", "duration": 14.8, "start": 3.5, "end": 18.3, "filepath": "/data/2.wav"},
    ])

    with test_db._connection() as conn:
        cursor = conn.cursor()
        # SQL assertion to verify all segments respect [2.0, 15.0] seconds bound
        cursor.execute("""
            SELECT COUNT(*) FROM segments 
            WHERE duration < 2.0 OR duration > 15.0
        """)
        invalid_segments_count = cursor.fetchone()[0]
        assert invalid_segments_count == 0, "No audio segment should be shorter than 2s or longer than 15s for ASR corpus"


def test_sql_index_performance_plan(test_db: Database):
    """TC-DB-06: Verify that indexing on crawl_batch and task_id is effectively utilized."""
    with test_db._connection() as conn:
        cursor = conn.cursor()
        
        # Check query plan for batch filtering
        cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM videos WHERE crawl_batch = 'WEEK3_0309'")
        rows = cursor.fetchall()
        # sqlite3.Row provides details
        details = " ".join([str(dict(r)) for r in rows]).lower()
        
        # SQLite query plan should mention idx_videos_batch or index
        assert "idx_videos_batch" in details or "index" in details, (
            f"Query plan did not utilize expected index: {details}"
        )
