#!/usr/bin/env python
"""Script để làm sạch URL, lọc trùng lặp liên batch và chuẩn hóa schema sang task."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

from src.config import get_config, resolve_path
from src.processing.transformer import export_records_to_csv, process_records
from src.processing.validator import validate_batch_name
from src.storage.json_storage import GlobalIndexManager, atomic_write_json, load_json


def confirm_input(input_file: Path, record_count: int) -> None:
    print(f"\nFile input: {input_file}")
    print(f"Số records: {record_count}")
    answer = input("Xác nhận xử lý file này? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")


def main():
    parser = argparse.ArgumentParser(description="Làm sạch URL video từ TikTok và chuẩn hóa task.")
    parser.add_argument("--input", help="Đường dẫn file raw JSON đầu vào.")
    parser.add_argument("--batch", help="Tên batch đầu ra theo định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309).")
    parser.add_argument("--index-file", help="Đường dẫn tùy chọn tới file chỉ mục toàn cục processed_index.json.")
    parser.add_argument("--yes", action="store_true", help="Bỏ qua xác nhận tương tác.")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử nghiệm không ghi đĩa.")
    args = parser.parse_args()

    config = get_config()
    processed_audio_dir = resolve_path(config.get("paths", {}).get("processed_audio_dir", "data/processed/audio"))
    output_json_dir = resolve_path(config.get("paths", {}).get("output_json_dir", "data/output/json"))
    output_csv_dir = resolve_path(config.get("paths", {}).get("output_csv_dir", "data/output/csv"))

    if not args.input:
        raw_dir = resolve_path(config.get("paths", {}).get("raw_data_dir", "data/raw/tiktok"))
        candidates = sorted(raw_dir.glob("**/raw_data*.json"))
        if not candidates:
            raise FileNotFoundError(f"Không tìm thấy file raw_data nào trong: {raw_dir}")
        input_file = candidates[-1]
        print(f"[*] Tự động chọn file raw mới nhất: {input_file}")
    else:
        input_file = Path(args.input).resolve()

    if not input_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy file input: {input_file}")

    date_match = re.search(r"(\d{4})", input_file.name)
    date_token = date_match.group(1) if date_match else datetime.now().strftime("%d%m")

    batch_name = args.batch
    if batch_name:
        if not validate_batch_name(batch_name):
            raise ValueError(f"Tên batch phải có định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309), nhận được: {batch_name}")
    elif validate_batch_name(input_file.parent.name):
        batch_name = input_file.parent.name
    else:
        batch_name = f"WEEK1_{date_token}"

    raw_data = load_json(input_file, default=[])
    if not isinstance(raw_data, list):
        raise ValueError("File đầu vào phải là danh sách JSON records.")

    if not args.yes:
        confirm_input(input_file, len(raw_data))

    index_mgr = GlobalIndexManager(index_path=args.index_file)
    global_index = index_mgr.load()

    tasks, rejected = process_records(raw_data, batch_name, global_index=global_index)

    target_dir = processed_audio_dir / batch_name
    target_dir.mkdir(parents=True, exist_ok=True)
    output_sources = target_dir / f"sources_{date_token}.json"

    report = {
        "input_file": str(input_file),
        "output_file": str(output_sources),
        "batch": batch_name,
        "total_records": len(raw_data),
        "valid_records": len(tasks),
        "rejected_records": len(rejected),
        "global_duplicates": sum(1 for item in rejected if item["reason"] == "global_duplicate_url"),
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        atomic_write_json(output_sources, tasks)
        atomic_write_json(target_dir / "summary.json", report)
        index_mgr.update_with_tasks(tasks, batch_name)

        # Lưu thêm bản sao ra output/
        atomic_write_json(output_json_dir / f"{batch_name}_tasks.json", tasks)
        export_records_to_csv(tasks, output_csv_dir / f"{batch_name}_tasks.csv")

    print(f"\n[+] {input_file.name}: {len(tasks)} hợp lệ, {len(rejected)} bị loại.")
    if not args.dry_run:
        print(f"[+] Output task: {output_sources}")
        print(f"[+] Output batch: {target_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[-] Lỗi: {e}")
        sys.exit(1)
