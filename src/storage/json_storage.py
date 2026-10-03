"""JSON storage manager with atomic writing and global index tracking."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import get_config, resolve_path


def atomic_write_json(path: str | Path, data: Any, indent: int = 2) -> None:
    """Ghi dữ liệu JSON theo cơ chế Atomic Write thông qua file tạm .part và rename."""
    target_path = Path(path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.part")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write("\n")

    os.replace(temp_path, target_path)


def load_json(path: str | Path, default: Any = None) -> Any:
    """Đọc dữ liệu từ file JSON an toàn."""
    target_path = Path(path).resolve()
    if not target_path.is_file() or target_path.stat().st_size == 0:
        return default
    try:
        with target_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


class GlobalIndexManager:
    """Quản lý chỉ mục toàn cục (processed_index.json) chống trùng lặp giữa các tuần/batch."""

    def __init__(self, index_path: Optional[str | Path] = None):
        config = get_config()
        if index_path:
            self.path = resolve_path(index_path)
        else:
            primary = resolve_path(config.get("paths", {}).get("global_index_path", "data/processed/metadata/processed_index.json"))
            fallback = resolve_path(config.get("paths", {}).get("fallback_index_path", "processed_index.json"))
            if primary.is_file():
                self.path = primary
            elif fallback.is_file():
                self.path = fallback
            else:
                self.path = primary

        self._lock = threading.Lock()
        self._data: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.is_file() or self.path.stat().st_size == 0:
                self._data = {"updated_at": None, "total_records": 0, "urls": {}}
                return self._data

            try:
                with self.path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "urls" in raw:
                    self._data = raw
                elif isinstance(raw, dict):
                    self._data = {"updated_at": None, "total_records": len(raw), "urls": raw}
                elif isinstance(raw, list):
                    self._data = {"updated_at": None, "total_records": len(raw), "urls": {u: {} for u in raw}}
                else:
                    self._data = {"updated_at": None, "total_records": 0, "urls": {}}
            except Exception as e:
                print(f"[!] Cảnh báo: Không thể nạp global index từ {self.path}: {e}")
                self._data = {"updated_at": None, "total_records": 0, "urls": {}}
            return self._data

    def has_url(self, url: str) -> bool:
        if self._data is None:
            self.load()
        return url in (self._data or {}).get("urls", {})

    def update_with_tasks(self, tasks: List[Dict[str, Any]], crawl_batch: str) -> None:
        if self._data is None:
            self.load()

        with self._lock:
            urls_map = self._data.setdefault("urls", {})
            now_iso = datetime.now(timezone.utc).isoformat()
            added = 0
            for task in tasks:
                url = task.get("original_url")
                if url:
                    urls_map[url] = {
                        "task_id": task.get("task_id"),
                        "item_id": task.get("item_id"),
                        "batch": crawl_batch,
                        "recorded_at": now_iso,
                    }
                    added += 1

            self._data["updated_at"] = now_iso
            self._data["total_records"] = len(urls_map)
            atomic_write_json(self.path, self._data)

            # Đồng bộ về cả fallback path nếu khác path chính
            config = get_config()
            fallback = resolve_path(config.get("paths", {}).get("fallback_index_path", "processed_index.json"))
            if fallback != self.path:
                try:
                    atomic_write_json(fallback, self._data)
                except Exception:
                    pass


class MetadataManager:
    """Quản lý metadata.json trong quá trình xử lý audio song song đa luồng."""

    def __init__(self, metadata_filepath: str | Path):
        self.filepath = Path(metadata_filepath).resolve()
        self.lock = threading.Lock()
        self.records_by_item: Dict[str, Dict[str, Any]] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        if self.filepath.is_file() and self.filepath.stat().st_size > 0:
            try:
                with self.filepath.open("r", encoding="utf-8") as f:
                    records = json.load(f)
                if isinstance(records, list):
                    for rec in records:
                        if rec.get("item_id"):
                            self.records_by_item[str(rec["item_id"])] = rec
            except Exception:
                pass

    def get_record(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.records_by_item.get(str(item_id))

    def update_record(self, record: Dict[str, Any]) -> None:
        with self.lock:
            item_id = str(record.get("item_id") or "")
            if item_id:
                self.records_by_item[item_id] = record

    def flush(self) -> None:
        with self.lock:
            records = sorted(self.records_by_item.values(), key=lambda r: r.get("item_id", ""))
            atomic_write_json(self.filepath, records)
