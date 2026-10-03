"""Pipeline orchestrator for TikTok data collection, cleaning, and speech audio extraction."""

import argparse
import json
import logging
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import get_config, resolve_path
from src.media.audio_processor import AudioProcessor
from src.processing.transformer import export_records_to_csv, process_records
from src.processing.validator import validate_batch_name
from src.storage.json_storage import GlobalIndexManager, atomic_write_json, load_json

# Setup logging
log_dir = resolve_path("logs")
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("Pipeline")


class PipelineRunner:
    """Điều phối toàn diện 3 giai đoạn của TikTok Data Pipeline."""

    def __init__(self, config_path: Optional[str | Path] = None):
        self.config = get_config()
        self.root_dir = resolve_path(".")
        self.raw_dir = resolve_path(self.config.get("paths", {}).get("raw_data_dir", "data/raw/tiktok"))
        self.processed_meta_dir = resolve_path(self.config.get("paths", {}).get("processed_metadata_dir", "data/processed/metadata"))
        self.processed_audio_dir = resolve_path(self.config.get("paths", {}).get("processed_audio_dir", "data/processed/audio"))
        self.output_json_dir = resolve_path(self.config.get("paths", {}).get("output_json_dir", "data/output/json"))
        self.output_csv_dir = resolve_path(self.config.get("paths", {}).get("output_csv_dir", "data/output/csv"))
        self.global_index = GlobalIndexManager()

    def determine_batch_name(self, batch_arg: Optional[str] = None) -> str:
        """Xác định hoặc sinh tên batch theo chuẩn WEEK<number>_<DDMM>."""
        if batch_arg:
            if not validate_batch_name(batch_arg):
                raise ValueError(f"Tên batch phải có định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309), nhận được: {batch_arg}")
            return batch_arg

        date_token = datetime.now().strftime("%d%m")
        return f"WEEK1_{date_token}"

    def run_crawl(
        self,
        spider_type: str = "hashtag",
        tags: Optional[str] = None,
        usernames: Optional[str] = None,
        max_scrolls: int = 5,
        batch_name: Optional[str] = None,
    ) -> Path:
        """Giai đoạn 1: Cào dữ liệu TikTok bằng Scrapy & Playwright."""
        batch = self.determine_batch_name(batch_name)
        date_token = datetime.now().strftime("%d%m")
        batch_raw_dir = self.raw_dir / batch
        batch_raw_dir.mkdir(parents=True, exist_ok=True)
        output_file = batch_raw_dir / f"raw_data{date_token}.json"

        logger.info(f"[*] Bắt đầu cào dữ liệu ({spider_type}) cho batch: {batch}")
        cmd = [
            sys.executable, "-m", "scrapy", "crawl", spider_type,
            "-a", f"max_scrolls={max_scrolls}",
            "-a", f"batch={batch_raw_dir}",
        ]
        if spider_type == "hashtag" and tags:
            cmd.extend(["-a", f"tags={tags}"])
        elif spider_type == "user" and usernames:
            cmd.extend(["-a", f"usernames={usernames}"])

        env = os.environ.copy()
        env["SCRAPY_SETTINGS_MODULE"] = "src.crawler.scrapy.settings"
        env["PYTHONPATH"] = str(self.root_dir)

        proc = subprocess.run(cmd, cwd=str(self.root_dir), env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"Lỗi khi thực thi crawler Scrapy (exit code: {proc.returncode})")

        logger.info(f"[+] Hoàn tất crawl dữ liệu. Kết quả tại: {output_file}")
        return output_file

    def run_process_urls(
        self,
        input_file: str | Path,
        batch_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Giai đoạn 2: Làm sạch URL, lọc trùng lặp liên batch và chuẩn hóa schema task."""
        input_path = Path(input_file).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file raw data: {input_path}")

        date_match = re.search(r"(\d{4})", input_path.name)
        date_token = date_match.group(1) if date_match else datetime.now().strftime("%d%m")
        batch = self.determine_batch_name(batch_name)

        target_batch_dir = self.processed_audio_dir / batch
        target_batch_dir.mkdir(parents=True, exist_ok=True)
        sources_file = target_batch_dir / f"sources_{date_token}.json"

        logger.info(f"[*] Làm sạch URL từ: {input_path.name}")
        raw_data = load_json(input_path, default=[])
        if not isinstance(raw_data, list):
            raise ValueError("Dữ liệu đầu vào phải là danh sách JSON records.")

        index_data = self.global_index.load()
        tasks, rejected = process_records(raw_data, batch, global_index=index_data)

        report = {
            "input_file": str(input_path),
            "output_file": str(sources_file),
            "batch": batch,
            "total_records": len(raw_data),
            "valid_records": len(tasks),
            "rejected_records": len(rejected),
            "global_duplicates": sum(1 for item in rejected if item["reason"] == "global_duplicate_url"),
            "dry_run": dry_run,
        }

        if not dry_run:
            atomic_write_json(sources_file, tasks)
            atomic_write_json(target_batch_dir / "summary.json", report)
            self.global_index.update_with_tasks(tasks, batch)
            # Đồng thời sao lưu sang data/output/
            atomic_write_json(self.output_json_dir / f"{batch}_tasks.json", tasks)
            export_records_to_csv(tasks, self.output_csv_dir / f"{batch}_tasks.csv")

        logger.info(f"[+] Đã xử lý: {len(tasks)} hợp lệ, {len(rejected)} loại bỏ.")
        return {
            "sources_file": str(sources_file),
            "batch_dir": str(target_batch_dir),
            "report": report,
            "tasks": tasks,
        }

    def run_media_pipeline(
        self,
        sources_file: str | Path,
        workers: int = 4,
        task_id: Optional[str] = None,
        enable_vad: bool = True,
    ) -> Dict[str, Any]:
        """Giai đoạn 3: Tải, chuẩn hóa loudnorm, tách nhạc UVR, khử nhiễu DPDFNet và cắt câu thoại Silero VAD."""
        sources_path = Path(sources_file).resolve()
        if not sources_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy sources file: {sources_path}")

        tasks = load_json(sources_path, default=[])
        if not isinstance(tasks, list):
            raise ValueError("Sources file phải là danh sách JSON tasks.")

        output_dir = sources_path.parent
        processor = AudioProcessor(output_dir)

        if task_id:
            selected = [t for t in tasks if t.get("task_id") == task_id]
            if not selected:
                raise ValueError(f"Không tìm thấy task_id: {task_id}")
            logger.info(f"[*] Xử lý riêng biệt task: {task_id}")
            result = processor.process_task(selected[0], enable_vad=enable_vad)
            return {"task_result": result}

        return processor.run_batch(tasks, max_workers=workers, enable_vad=enable_vad)

    def run_all(
        self,
        spider_type: str = "hashtag",
        tags: Optional[str] = None,
        usernames: Optional[str] = None,
        max_scrolls: int = 5,
        batch_name: Optional[str] = None,
        workers: int = 4,
        enable_vad: bool = True,
    ) -> Dict[str, Any]:
        """Chạy toàn bộ pipeline khép kín từ cào đến bóc tách audio hoàn chỉnh."""
        batch = self.determine_batch_name(batch_name)
        logger.info(f"=== BẮT ĐẦU END-TO-END PIPELINE: {batch} ===")

        raw_file = self.run_crawl(
            spider_type=spider_type,
            tags=tags,
            usernames=usernames,
            max_scrolls=max_scrolls,
            batch_name=batch,
        )

        process_result = self.run_process_urls(
            input_file=raw_file,
            batch_name=batch,
        )

        sources_file = process_result["sources_file"]
        media_result = self.run_media_pipeline(
            sources_file=sources_file,
            workers=workers,
            enable_vad=enable_vad,
        )

        logger.info(f"=== HOÀN TẤT END-TO-END PIPELINE: {batch} ===")
        return {
            "batch": batch,
            "raw_file": str(raw_file),
            "sources_file": sources_file,
            "media_result": media_result,
        }


def main():
    parser = argparse.ArgumentParser(description="TikTok Data Pipeline Manager")
    parser.add_argument(
        "--mode",
        choices=["crawl", "process", "media", "all"],
        default="all",
        help="Chế độ thực thi: crawl (cào), process (lọc URL), media (xử lý audio), all (toàn bộ).",
    )
    parser.add_argument("--batch", help="Tên batch theo định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309).")
    parser.add_argument("--tags", help="Danh sách hashtag phân cách bằng dấu phẩy (cho crawl).")
    parser.add_argument("--usernames", help="Danh sách username TikTok phân cách bằng dấu phẩy (cho crawl).")
    parser.add_argument("--max-scrolls", type=int, default=5, help="Số lần cuộn trang khi cào.")
    parser.add_argument("--input", help="Đường dẫn file đầu vào cho process hoặc media.")
    parser.add_argument("--workers", type=int, default=4, help="Số worker xử lý audio song song (tối đa 8).")
    parser.add_argument("--task-id", help="Chỉ xử lý một task_id duy nhất trong media mode.")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử nghiệm không ghi đĩa.")
    parser.add_argument("--no-vad", action="store_true", help="Bỏ qua phân đoạn câu thoại Silero VAD.")

    args = parser.parse_args()
    runner = PipelineRunner()
    enable_vad = not args.no_vad

    if args.mode == "crawl":
        spider = "user" if args.usernames else "hashtag"
        out = runner.run_crawl(
            spider_type=spider,
            tags=args.tags,
            usernames=args.usernames,
            max_scrolls=args.max_scrolls,
            batch_name=args.batch,
        )
        print(f"[+] File cào: {out}")

    elif args.mode == "process":
        if not args.input:
            raise ValueError("Cần truyền --input file JSON dữ liệu cào.")
        res = runner.run_process_urls(args.input, batch_name=args.batch, dry_run=args.dry_run)
        print(json.dumps(res["report"], indent=2, ensure_ascii=False))

    elif args.mode == "media":
        if not args.input:
            raise ValueError("Cần truyền --input file sources_DDMM.json.")
        res = runner.run_media_pipeline(
            sources_file=args.input,
            workers=args.workers,
            task_id=args.task_id,
            enable_vad=enable_vad,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.mode == "all":
        spider = "user" if args.usernames else "hashtag"
        res = runner.run_all(
            spider_type=spider,
            tags=args.tags or "tintuc,giaitri",
            usernames=args.usernames,
            max_scrolls=args.max_scrolls,
            batch_name=args.batch,
            workers=args.workers,
            enable_vad=enable_vad,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"[-] Lỗi pipeline: {e}")
        sys.exit(1)
