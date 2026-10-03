"""SQLite database manager for persistent pipeline metadata and segments."""

import contextlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from src.config import get_config, resolve_path


class Database:
    """Quản lý cơ sở dữ liệu SQLite cho pipeline dữ liệu TikTok."""

    def __init__(self, db_path: Optional[str | Path] = None):
        config = get_config()
        self.db_path = resolve_path(db_path or config.get("storage", {}).get("database_path", "data/pipeline.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.init_db()

    @contextlib.contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager tạo connection và tự động close sau khi xong."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def close(self) -> None:
        """Đóng database (nếu cần giải phóng tài nguyên)."""
        pass

    def init_db(self) -> None:
        """Khởi tạo bảng cơ sở dữ liệu nếu chưa tồn tại."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.executescript("""
                    CREATE TABLE IF NOT EXISTS global_index (
                        url TEXT PRIMARY KEY,
                        task_id TEXT,
                        item_id TEXT,
                        batch TEXT,
                        recorded_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS videos (
                        task_id TEXT PRIMARY KEY,
                        item_id TEXT,
                        platform TEXT,
                        original_url TEXT,
                        title TEXT,
                        duration_seconds REAL,
                        language_region TEXT,
                        crawl_batch TEXT,
                        crawled_at TEXT,
                        status TEXT DEFAULT 'pending',
                        error_message TEXT,
                        audio_path TEXT,
                        metadata_json TEXT
                    );

                    CREATE TABLE IF NOT EXISTS segments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        filename TEXT,
                        duration REAL,
                        start_time REAL,
                        end_time REAL,
                        filepath TEXT,
                        FOREIGN KEY (task_id) REFERENCES videos(task_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_videos_batch ON videos(crawl_batch);
                    CREATE INDEX IF NOT EXISTS idx_segments_task ON segments(task_id);
                """)
                conn.commit()

    def has_url(self, url: str) -> bool:
        """Kiểm tra URL đã tồn tại trong chỉ mục toàn cục hay chưa."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM global_index WHERE url = ? LIMIT 1", (url,))
                return cursor.fetchone() is not None

    def insert_task(self, task: Dict[str, Any]) -> None:
        """Thêm task video vào database."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO videos (
                        task_id, item_id, platform, original_url, title,
                        duration_seconds, language_region, crawl_batch,
                        crawled_at, status, audio_path, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.get("task_id"),
                    task.get("item_id"),
                    task.get("platform", "tiktok"),
                    task.get("original_url"),
                    task.get("title", ""),
                    task.get("duration_seconds"),
                    task.get("language_region", "unidentified"),
                    task.get("crawl_batch"),
                    task.get("crawled_at"),
                    task.get("status", "pending"),
                    task.get("audio_path"),
                    json.dumps(task, ensure_ascii=False),
                ))

                if task.get("original_url"):
                    cursor.execute("""
                        INSERT OR REPLACE INTO global_index (url, task_id, item_id, batch, recorded_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        task["original_url"],
                        task.get("task_id"),
                        task.get("item_id"),
                        task.get("crawl_batch"),
                        task.get("crawled_at"),
                    ))
                conn.commit()

    def save_segments(self, task_id: str, segments: List[Dict[str, Any]]) -> None:
        """Lưu danh sách segments được cắt bởi VAD."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                for seg in segments:
                    cursor.execute("""
                        INSERT INTO segments (task_id, filename, duration, start_time, end_time, filepath)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        task_id,
                        seg.get("filename"),
                        seg.get("duration"),
                        seg.get("start"),
                        seg.get("end"),
                        seg.get("filepath", seg.get("filename")),
                    ))
                conn.commit()

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: str = "",
        audio_path: str = "",
    ) -> None:
        """Cập nhật trạng thái xử lý của task."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE videos
                    SET status = ?, error_message = ?, audio_path = CASE WHEN ? != '' THEN ? ELSE audio_path END
                    WHERE task_id = ?
                """, (status, error_message, audio_path, audio_path, task_id))
                conn.commit()

    def get_batch_tasks(self, batch_name: str) -> List[Dict[str, Any]]:
        """Lấy tất cả task thuộc 1 batch."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM videos WHERE crawl_batch = ?", (batch_name,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
