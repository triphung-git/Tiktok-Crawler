#!/usr/bin/env python
"""
Legacy wrapper for core_worker.py.
Delegates to modular AudioProcessor in src.media.audio_processor.
Preserves 100% backward compatibility for all existing scripts and CLI commands.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, resolve_path
from src.media.audio_downloader import download_audio
from src.media.audio_processor import AudioProcessor, Heartbeat
from src.processing.validator import classify_error
from src.storage.json_storage import atomic_write_json, load_json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

CURRENT_DIR = str(PROJECT_ROOT)
FFMPEG_PATH = str(resolve_path("ffmpeg.exe"))
FFPROBE_PATH = str(resolve_path("ffprobe.exe"))


def load_tasks(input_file: str) -> list[dict[str, Any]]:
    tasks = load_json(input_file)
    if not isinstance(tasks, list):
        raise ValueError("sources.json phải chứa một JSON array.")
    return tasks


def find_input_file(directory: str) -> str:
    candidates = sorted(
        os.path.join(directory, name) for name in os.listdir(directory)
        if re.fullmatch(r"sources_\d{4}(?:_\d{2})?\.json", name)
    )
    if not candidates:
        raise FileNotFoundError(f"Không tìm thấy sources_DDMM.json trong: {directory}")
    if len(candidates) == 1:
        return candidates[0]
    print("Các file input tìm thấy:")
    for index, candidate in enumerate(candidates, 1):
        print(f"  {index}. {os.path.basename(candidate)}")
    choice = input("Chọn số file input: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(candidates):
        raise ValueError("Lựa chọn file input không hợp lệ.")
    return candidates[int(choice) - 1]


def confirm_input(input_file: str) -> None:
    print(f"\nThư mục xử lý: {os.path.dirname(os.path.abspath(input_file))}")
    print(f"File input: {os.path.basename(input_file)}")
    print(f"Số task: {len(load_tasks(input_file))}")
    if input("Bắt đầu xử lý file này? [y/N]: ").strip().lower() not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tải, chuẩn hóa, khử nhiễu và phân đoạn audio theo batch.")
    parser.add_argument("--input", help="Đường dẫn file sources JSON.")
    parser.add_argument("--directory", default=CURRENT_DIR, help="Thư mục chứa sources_DDMM.json.")
    parser.add_argument("--batch", help="Tên thư mục output bắt buộc WEEK<number>_<DDMM> (ví dụ: WEEK3_0309).")
    parser.add_argument("--workers", type=int, default=4, help="Số worker đồng thời, tối đa 8.")
    parser.add_argument("--task-id", help="Chỉ xử lý một task_id.")
    parser.add_argument("--yes", action="store_true", help="Bỏ qua xác nhận tương tác; dùng cho tự động hóa.")
    parser.add_argument("--ignore-env-proxy", action="store_true", help="Bỏ qua HTTP(S)_PROXY/ALL_PROXY của môi trường.")
    args = parser.parse_args()

    if args.ignore_env_proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)
        os.environ["YTDLP_PROXY"] = ""

    input_file = os.path.abspath(args.input) if args.input else os.path.abspath(find_input_file(args.directory))
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Không tìm thấy file input: {input_file}")

    if not args.yes:
        confirm_input(input_file)

    output_dir = os.path.dirname(input_file)
    if args.batch:
        if not re.fullmatch(r"WEEK\d+_\d{4}", args.batch, re.IGNORECASE):
            raise ValueError(f"Tên batch phải có định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309), nhận được: {args.batch}")
        output_dir = os.path.join(CURRENT_DIR, args.batch)

    processor = AudioProcessor(output_dir)
    tasks = load_tasks(input_file)

    if args.task_id:
        selected = [t for t in tasks if t.get("task_id") == args.task_id]
        if not selected:
            raise ValueError(f"Không tìm thấy task_id: {args.task_id}")
        res = processor.process_task(selected[0])
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    result = processor.run_batch(tasks, max_workers=args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"[-] {error}")
