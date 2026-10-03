#!/usr/bin/env python
"""Script thực thi pipeline xử lý audio hoặc điều phối toàn diện end-to-end."""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

from src.config import get_config, resolve_path
from src.media.audio_processor import AudioProcessor
from src.pipeline.run import PipelineRunner
from src.storage.json_storage import load_json


def confirm_input(input_file: Path, task_count: int) -> None:
    print(f"\nThư mục xử lý: {input_file.parent}")
    print(f"File sources: {input_file.name}")
    print(f"Số lượng tasks: {task_count}")
    answer = input("Bắt đầu xử lý audio cho file này? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")


def main():
    parser = argparse.ArgumentParser(description="TikTok Data Pipeline Runner CLI")
    parser.add_argument("--mode", choices=["media", "all", "crawl", "process"], default="media",
                        help="Chế độ thực thi: 'media' (mặc định), 'all', 'crawl', 'process'.")
    parser.add_argument("--input", help="Đường dẫn file sources_DDMM.json (cho mode media).")
    parser.add_argument("--batch", help="Tên batch output WEEK<number>_<DDMM>.")
    parser.add_argument("--workers", type=int, default=4, help="Số worker xử lý audio song song (1-8).")
    parser.add_argument("--task-id", help="Chỉ xử lý riêng một task_id duy nhất.")
    parser.add_argument("--yes", action="store_true", help="Bỏ qua xác nhận tương tác.")
    parser.add_argument("--ignore-env-proxy", action="store_true", help="Bỏ qua proxy môi trường hệ thống.")
    parser.add_argument("--no-vad", action="store_true", help="Không cắt lát câu thoại tự nhiên bằng Silero VAD.")

    # Crawler options
    parser.add_argument("--tags", help="Tags để cào video (cho mode all/crawl).")
    parser.add_argument("--usernames", help="Usernames để cào video (cho mode all/crawl).")
    parser.add_argument("--max-scrolls", type=int, default=5, help="Số lần cuộn trang.")
    args = parser.parse_args()

    if args.ignore_env_proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)
        os.environ["YTDLP_PROXY"] = ""

    runner = PipelineRunner()
    enable_vad = not args.no_vad

    if args.mode in {"all", "crawl", "process"}:
        if args.mode == "crawl":
            spider = "user" if args.usernames else "hashtag"
            out = runner.run_crawl(spider_type=spider, tags=args.tags, usernames=args.usernames,
                                  max_scrolls=args.max_scrolls, batch_name=args.batch)
            print(f"[+] Hoàn tất crawl: {out}")
        elif args.mode == "process":
            if not args.input:
                raise ValueError("Cần truyền --input file raw JSON.")
            res = runner.run_process_urls(args.input, batch_name=args.batch)
            print(json.dumps(res["report"], indent=2, ensure_ascii=False))
        elif args.mode == "all":
            spider = "user" if args.usernames else "hashtag"
            res = runner.run_all(spider_type=spider, tags=args.tags, usernames=args.usernames,
                                max_scrolls=args.max_scrolls, batch_name=args.batch,
                                workers=args.workers, enable_vad=enable_vad)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    # Default Mode: Media (Core Worker)
    config = get_config()
    processed_dir = resolve_path(config.get("paths", {}).get("processed_audio_dir", "data/processed/audio"))

    if args.input:
        sources_path = Path(args.input).resolve()
    else:
        # Tự động tìm sources_DDMM.json gần nhất
        candidates = sorted(processed_dir.glob("**/sources_*.json"))
        if not candidates:
            # Tìm ở thư mục gốc nếu có batch cũ
            candidates = sorted(PROJECT_ROOT.glob("**/sources_*.json"))
        if not candidates:
            raise FileNotFoundError(f"Không tìm thấy file sources_DDMM.json nào trong {processed_dir} hoặc project root.")
        sources_path = candidates[-1]
        print(f"[*] Tự động chọn file sources: {sources_path}")

    if not sources_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file input: {sources_path}")

    tasks = load_json(sources_path, default=[])
    if not isinstance(tasks, list):
        raise ValueError("Sources file phải chứa một danh sách JSON tasks.")

    if not args.yes and not args.task_id:
        confirm_input(sources_path, len(tasks))

    output_dir = sources_path.parent
    processor = AudioProcessor(output_dir)

    if args.task_id:
        selected = [t for t in tasks if t.get("task_id") == args.task_id]
        if not selected:
            raise ValueError(f"Không tìm thấy task_id: {args.task_id}")
        res = processor.process_task(selected[0], enable_vad=enable_vad)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    summary = processor.run_batch(tasks, max_workers=args.workers, enable_vad=enable_vad)
    print("\n=== KẾT QUẢ XỬ LÝ BATCH ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[-] Lỗi thực thi: {e}")
        sys.exit(1)
