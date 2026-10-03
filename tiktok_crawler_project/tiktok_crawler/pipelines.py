import json
import os
from datetime import datetime, timezone

from scrapy.exceptions import DropItem


class JsonExportPipeline:
    """
    Gom toàn bộ item trong 1 lần chạy spider, loại bỏ video_url trùng lặp,
    chuẩn hóa schema tương thích với url_processor, và ghi ra file JSON
    trong thư mục batch (WEEKnumber_DDMM) hoặc thư mục output/ khi spider đóng.
    """

    def __init__(self):
        self.seen_urls = set()
        self.items = []
        self.filepath = None

    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls()
        pipeline.crawler = crawler
        return pipeline

    def open_spider(self, spider=None):
        spider = spider or (getattr(self, "crawler", None) and self.crawler.spider)
        # Hỗ trợ truyền batch qua argument: scrapy crawl hashtag -a batch=WEEK3_0309
        batch_name = getattr(spider, "batch", None) or os.getenv("BATCH_NAME")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        date_token = datetime.now().strftime("%d%m")

        if batch_name:
            out_dir = batch_name
            os.makedirs(out_dir, exist_ok=True)
            self.filepath = os.path.join(out_dir, f"raw_data{date_token}.json")
        else:
            os.makedirs("output", exist_ok=True)
            spider_name = spider.name if spider else "crawler"
            self.filepath = os.path.join("output", f"{spider_name}_{timestamp}.json")

    def process_item(self, item, spider=None):
        url = item.get("video_url")
        if not url:
            raise DropItem("Item không có video_url")
        if url in self.seen_urls:
            raise DropItem(f"URL trùng lặp: {url}")
        self.seen_urls.add(url)

        # Chuẩn hóa dữ liệu tương thích đồng thời cả Scrapy Item và url_processor
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
        msg = f"Đã ghi {len(self.items)} item vào {self.filepath}"
        if spider:
            spider.logger.info(msg)
