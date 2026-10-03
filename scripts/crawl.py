#!/usr/bin/env python
"""Script để kích hoạt crawler cào video TikTok theo hashtag hoặc username."""

import argparse
import os
import subprocess
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
from src.processing.validator import validate_batch_name


def main():
    parser = argparse.ArgumentParser(description="TikTok Crawler CLI Script")
    parser.add_argument("--tags", help="Danh sách hashtag phân cách bằng dấu phẩy (ví dụ: 'tintuc,giaitri').")
    parser.add_argument("--usernames", help="Danh sách username TikTok phân cách bằng dấu phẩy (ví dụ: 'vtv24news').")
    parser.add_argument("--max-scrolls", type=int, default=5, help="Số lần cuộn trang infinite scroll.")
    parser.add_argument("--batch", help="Tên batch theo định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309).")
    parser.add_argument("--spider", choices=["hashtag", "user"], help="Chỉ định spider cụ thể (mặc định tự chọn theo tags/usernames).")
    args = parser.parse_args()

    config = get_config()
    raw_base_dir = resolve_path(config.get("paths", {}).get("raw_data_dir", "data/raw/tiktok"))

    batch_name = args.batch
    if batch_name:
        if not validate_batch_name(batch_name):
            raise ValueError(f"Tên batch phải có định dạng WEEK<number>_<DDMM> (ví dụ: WEEK3_0309), nhận được: {batch_name}")
    else:
        date_token = datetime.now().strftime("%d%m")
        batch_name = f"WEEK1_{date_token}"

    spider = args.spider
    if not spider:
        spider = "user" if args.usernames else "hashtag"

    out_dir = raw_base_dir / batch_name
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "scrapy", "crawl", spider,
        "-a", f"max_scrolls={args.max_scrolls}",
        "-a", f"batch={out_dir}",
    ]
    if spider == "hashtag":
        tags = args.tags or "tintuc,giaitri"
        cmd.extend(["-a", f"tags={tags}"])
    elif spider == "user":
        if not args.usernames:
            raise ValueError("Cần truyền --usernames cho spider user.")
        cmd.extend(["-a", f"usernames={args.usernames}"])

    print(f"[*] Bắt đầu crawl TikTok ({spider})...")
    print(f"[*] Thư mục đích: {out_dir}")

    env = os.environ.copy()
    env["SCRAPY_SETTINGS_MODULE"] = "src.crawler.scrapy.settings"
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if proc.returncode != 0:
        print(f"[-] Crawler kết thúc với mã lỗi: {proc.returncode}")
        sys.exit(proc.returncode)
    print(f"[+] Hoàn tất crawl dữ liệu.")


if __name__ == "__main__":
    main()
