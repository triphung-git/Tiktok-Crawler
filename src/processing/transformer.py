"""Data transformation, task building, and record processing."""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.processing.cleaner import extract_video_id, format_duration, infer_regional_dialect
from src.processing.validator import validate_record


def build_task(
    item: Dict[str, Any],
    clean_url: str,
    platform: str,
    task_number: int,
    crawl_batch: str,
    crawled_at: str,
) -> Dict[str, Any]:
    """Chuyển đổi 1 raw record thành 1 task chuẩn hóa cho audio processor."""
    video_meta = item.get("videoMeta") or {}
    duration_seconds = (
        item.get("videoMeta.duration")
        or video_meta.get("duration")
        or item.get("duration")
        or item.get("duration_seconds")
    )
    raw_text = (
        item.get("text")
        or item.get("caption")
        or item.get("title")
        or item.get("description")
        or ""
    )
    text_language = item.get("textLanguage") or item.get("language") or "unknown"
    language_region = infer_regional_dialect(raw_text)
    platform_video_id = extract_video_id(clean_url, item, platform)
    subtitle_links = item.get("videoMeta.subtitleLinks", video_meta.get("subtitleLinks")) or []
    platform_prefix = {"tiktok": "tt", "youtube": "yt", "facebook": "fb"}.get(platform, "tt")

    return {
        "task_id": f"ID_{task_number:04d}",
        "item_id": f"{platform_prefix}_{platform_video_id}",
        "platform": platform,
        "platform_video_id": platform_video_id,
        "original_url": clean_url,
        "title": raw_text,
        "description": raw_text,
        "posted_at": item.get("createTimeISO") or item.get("scraped_at"),
        "duration_seconds": duration_seconds,
        "duration_formatted": format_duration(duration_seconds),
        "text_language": text_language,
        "language_raw": text_language,
        "language_region": language_region,
        "crawl_batch": crawl_batch,
        "crawled_at": item.get("crawled_at") or item.get("scraped_at") or crawled_at,
        "platform_meta": {
            "music_is_original": bool(
                item.get("musicMeta.musicOriginal", (item.get("musicMeta") or {}).get("musicOriginal", False))
            ),
            "is_duet": bool(item.get("isDuet", False)),
            "is_stitch": bool(item.get("isStitch", False)),
            "has_platform_captions": bool(subtitle_links),
            "author": item.get("author") or item.get("username") or (item.get("authorMeta") or {}).get("name", ""),
        },
    }


def process_records(
    data: List[Any],
    crawl_batch: str,
    global_index: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Xử lý danh sách records thô:
    - Lọc trùng lặp in-batch và cross-batch
    - Kiểm định tính hợp lệ
    - Sinh danh sách task hợp lệ và danh sách rejected records
    """
    tasks: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen_urls: set = set()
    global_urls = set((global_index or {}).get("urls", {}).keys())
    crawled_at = datetime.now(timezone.utc).isoformat()

    for index, item in enumerate(data, start=1):
        is_valid, clean_url, platform, video_id, reject_dict = validate_record(
            item, index, seen_urls=seen_urls, global_urls=global_urls
        )
        if not is_valid:
            if reject_dict:
                rejected.append(reject_dict)
            continue

        seen_urls.add(clean_url)
        task = build_task(item, clean_url, platform, len(tasks) + 1, crawl_batch, crawled_at)
        tasks.append(task)

    return tasks, rejected


def export_records_to_csv(records: List[Dict[str, Any]], output_path: str | Path) -> None:
    """Xuất danh sách records ra file CSV."""
    if not records:
        return
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(records[0].keys())
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            # Flatten or serialize complex dicts if needed
            row = {}
            for k, v in r.items():
                if isinstance(v, (dict, list)):
                    import json
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
            writer.writerow(row)
