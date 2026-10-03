"""Scrapy item pipelines for exporting crawled TikTok data."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Set
from scrapy.exceptions import DropItem

from src.config import get_config, resolve_path


class JsonExportPipeline:
    """
    Gom toàn bộ item trong 1 lần chạy spider, loại bỏ video_url trùng lặp,
    chuẩn hóa schema tương thích với bộ xử lý url_processor/cleaner,
    và ghi ra file JSON theo cơ chế atomic write.
    """

    def __init__(self):
        self.seen_urls: Set[str] = set()
        self.items: List[dict] = []
        self.filepath: Optional[str] = None

    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls()
        pipeline.crawler = crawler
        return pipeline

    def open_spider(self, spider=None):
        spider = spider or (getattr(self, "crawler", None) and self.crawler.spider)
        config = get_config()
        raw_base_dir = resolve_path(config.get("paths", {}).get("raw_data_dir", "data/raw/tiktok"))

        batch_name = getattr(spider, "batch", None) or os.getenv("BATCH_NAME")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        date_token = datetime.now().strftime("%d%m")

        if batch_name:
            out_dir = raw_base_dir / batch_name if not Path(batch_name).is_absolute() else Path(batch_name)
            out_dir.mkdir(parents=True, exist_ok=True)
            self.filepath = str(out_dir / f"raw_data{date_token}.json")
        else:
            raw_base_dir.mkdir(parents=True, exist_ok=True)
            spider_name = spider.name if spider else "crawler"
            self.filepath = str(raw_base_dir / f"{spider_name}_{timestamp}.json")

    def process_item(self, item, spider=None):
        url = item.get("video_url") or item.get("webVideoUrl")
        if not url:
            raise DropItem("Item không có video_url")
        if url in self.seen_urls:
            raise DropItem(f"URL trùng lặp trong phiên cào: {url}")
        self.seen_urls.add(url)

        item_dict = dict(item)
        if "webVideoUrl" not in item_dict:
            item_dict["webVideoUrl"] = url
        if "text" not in item_dict:
            item_dict["text"] = item_dict.get("hashtag") or item_dict.get("username") or ""
        if "createTimeISO" not in item_dict:
            item_dict["createTimeISO"] = item_dict.get("scraped_at")

        self.items.append(item_dict)
        return item

    def close_spider(self, spider=None):
        spider = spider or (getattr(self, "crawler", None) and self.crawler.spider)
        if not self.filepath:
            return

        temp_path = f"{self.filepath}.part"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, self.filepath)

        msg = f"Đã xuất an toàn {len(self.items)} item vào: {self.filepath}"
        if spider:
            spider.logger.info(msg)
        else:
            print(f"[+] {msg}")
