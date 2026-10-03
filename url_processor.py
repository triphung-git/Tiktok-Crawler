#!/usr/bin/env python
"""
Legacy wrapper for url_processor.py.
Delegates to modular components in src.processing and src.storage.
Preserves 100% backward compatibility for all existing scripts and CLI commands.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, resolve_path
from src.processing.cleaner import (
    REGIONAL_MARKERS,
    detect_platform,
    extract_video_id,
    format_duration,
    infer_regional_dialect,
    sanitize_tiktok_url,
    sanitize_video_url,
)
from src.processing.transformer import build_task, process_records
from src.processing.validator import reject_record
from src.storage.json_storage import (
    GlobalIndexManager,
    atomic_write_json,
    load_json,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

DEFAULT_INDEX_PATH = PROJECT_ROOT / "processed_index.json"


def load_processed_index(index_path: Path = DEFAULT_INDEX_PATH) -> dict[str, Any]:
    mgr = GlobalIndexManager(index_path=index_path)
    return mgr.load()


def update_processed_index(index_path: Path, new_tasks: list[dict[str, Any]], crawl_batch: str) -> None:
    mgr = GlobalIndexManager(index_path=index_path)
    mgr.update_with_tasks(new_tasks, crawl_batch)


def next_output_path(directory: Path, date_token: str) -> Path:
    base = directory / f"sources_{date_token}.json"
    if not base.exists():
        return base
    suffix = 1
    while True:
        candidate = directory / f"sources_{date_token}_{suffix:02d}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def find_input_file(directory: Path) -> tuple[Path, str]:
    candidates = sorted(directory.glob("raw_data[0-9][0-9][0-9][0-9].json"))
    if not candidates:
        raise FileNotFoundError(
            f"Không tìm thấy file raw_dataDDMM.json trong thư mục: {directory}"
        )
    if len(candidates) > 1:
        names = ", ".join(candidate.name for candidate in candidates)
        raise ValueError(
            f"Thư mục có nhiều file input ({names}). Hãy dùng --input để chọn một file."
        )
    selected = candidates[0]
    date_token = re.fullmatch(r"raw_data(\d{4})\.json", selected.name).group(1)
    return selected, date_token


def load_input_records(input_file: Path) -> list[dict[str, Any]]:
    return load_json(input_file, default=[])


def confirm_input(input_file: Path, record_count: int) -> None:
    print(f"\nFile input: {input_file}")
    print(f"Số records: {record_count}")
    answer = input("Xác nhận xử lý file này? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")


def process_and_export_urls(
    input_file: str,
    output_file: str,
    dry_run: bool = False,
    index_file: Optional[str] = None,
    crawl_batch: Optional[str] = None,
) -> dict[str, Any]:
    input_path = Path(input_file)
    data = load_input_records(input_path)
    idx_path = Path(index_file) if index_file else DEFAULT_INDEX_PATH
    global_index = load_processed_index(idx_path)
    batch_name = crawl_batch or os.getenv("CRAWL_BATCH", "tt_batch_01")

    tasks, rejected = process_records(
        data,
        batch_name,
        global_index=global_index,
    )
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "batch": batch_name,
        "total_records": len(data),
        "valid_records": len(tasks),
        "rejected_records": len(rejected),
        "reasons": dict(Counter(item["reason"] for item in rejected)),
        "global_duplicates": sum(1 for item in rejected if item["reason"] == "global_duplicate_url"),
        "dry_run": dry_run,
    }
    if not dry_run:
        atomic_write_json(output_path, tasks)
        atomic_write_json(output_path.parent / "summary.json", report)
        update_processed_index(idx_path, tasks, batch_name)

    print(f"[+] {input_path.name}: {len(tasks)} hợp lệ, {len(rejected)} bị loại.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Làm sạch URL video từ TikTok, YouTube và Facebook."
    )
    parser.add_argument(
        "--directory",
        default=".",
        help="Thư mục cần xử lý; mặc định là thư mục hiện tại.",
    )
    parser.add_argument(
        "--input",
        help="Xử lý chính xác một file input JSON (raw_dataDDMM.json hoặc crawler output); ghi đè --directory.",
    )
    parser.add_argument(
        "--batch",
        help="Tên thư mục batch đầu ra theo định dạng bắt buộc WEEK<number>_<DDMM> (ví dụ: WEEK3_0309).",
    )
    parser.add_argument(
        "--index-file",
        help="Đường dẫn file chỉ mục toàn cục processed_index.json.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Bỏ qua xác nhận tương tác; dùng cho tự động hóa.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ kiểm tra và in báo cáo, không ghi output.",
    )
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục: {root}")

    if args.input:
        selected_input = Path(args.input).resolve()
        if not selected_input.is_file():
            raise FileNotFoundError(f"Không tìm thấy file input: {selected_input}")
        match = re.search(r"(\d{4})", selected_input.name)
        date_token = match.group(1) if match else datetime.now().strftime("%d%m")
        input_file = selected_input
    else:
        input_file, date_token = find_input_file(root)

    batch_name = args.batch
    if batch_name:
        if not re.fullmatch(r"WEEK\d+_\d{4}", batch_name, re.IGNORECASE):
            raise ValueError(f"Tên batch phải có định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309), nhận được: {batch_name}")
        batch_dir = root / batch_name
    elif re.fullmatch(r"WEEK\d+_\d{4}", input_file.parent.name, re.IGNORECASE):
        batch_name = input_file.parent.name
        batch_dir = input_file.parent
    else:
        batch_name = f"WEEK1_{date_token}"
        batch_dir = root / batch_name

    batch_dir.mkdir(parents=True, exist_ok=True)
    record_count = len(load_input_records(input_file))
    if not args.yes:
        confirm_input(input_file, record_count)
    output_file = next_output_path(batch_dir, date_token)
    process_and_export_urls(
        str(input_file),
        str(output_file),
        dry_run=args.dry_run,
        index_file=args.index_file,
        crawl_batch=batch_name,
    )
    if not args.dry_run:
        print(f"[+] Output batch: {batch_dir}")
        print(f"[+] Output file: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"[-] {error}")