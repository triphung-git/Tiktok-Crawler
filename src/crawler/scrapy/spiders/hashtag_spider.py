"""Hashtag spider for TikTok crawling."""

import json
from datetime import datetime, timezone
import scrapy

try:
    from src.crawler.scrapy.items import HashtagItem
except ModuleNotFoundError:
    from tiktok_crawler.items import HashtagItem


class HashtagSpider(scrapy.Spider):
    """
    Crawl danh sách video URL theo hashtag trên TikTok.

    Cách chạy:
        scrapy crawl hashtag -a tags="tintuc,giaitri" -a max_scrolls=8 -a batch=WEEK3_0309
    """

    name = "hashtag"
    allowed_domains = ["tiktok.com"]

    def __init__(self, tags=None, max_scrolls=5, batch=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tags = [t.strip().lstrip("#") for t in tags.split(",")] if tags else []
        self.max_scrolls = int(max_scrolls)
        self.batch = batch

    async def start(self):
        for req in self.start_requests():
            yield req

    def start_requests(self):
        if not self.tags:
            self.logger.error("Chưa truyền hashtag nào. Dùng: -a tags=tag1,tag2")
            return

        for tag in self.tags:
            url = f"https://www.tiktok.com/tag/{tag}"
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": "default",
                    "playwright_page_goto_kwargs": {
                        "wait_until": "domcontentloaded",
                    },
                    "hashtag": tag,
                },
                callback=self.parse_hashtag,
                errback=self.errback,
            )

    async def parse_hashtag(self, response):
        page = response.meta["playwright_page"]
        hashtag = response.meta["hashtag"]

        try:
            try:
                await page.wait_for_selector("a[href*='/video/']", state="attached", timeout=6000)
            except Exception:
                pass

            # Cuộn trang để kích hoạt lazy-load thêm video (infinite scroll)
            for _ in range(self.max_scrolls):
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1500)

            # Lấy html đã render
            html = await page.content()
        finally:
            await page.close()

        sel = scrapy.Selector(text=html)
        video_links = set(sel.css("a[href*='/video/']::attr(href)").getall())

        # Trích xuất thêm từ khối JSON state nhúng
        json_links = self._extract_from_embedded_json(sel)
        video_links.update(json_links)

        for link in video_links:
            item = HashtagItem()
            item["hashtag"] = hashtag
            item["video_url"] = link if link.startswith("http") else f"https://www.tiktok.com{link}"
            item["author"] = self._extract_author(link)
            item["scraped_at"] = datetime.now(timezone.utc).isoformat()
            item["source_type"] = "hashtag"
            yield item

    @staticmethod
    def _extract_author(url: str):
        try:
            return url.split("/video/")[0].split("@")[-1]
        except Exception:
            return None

    @staticmethod
    def _extract_from_embedded_json(sel):
        """Đọc thêm URL video từ JSON state nhúng trong HTML."""
        links = set()
        raw = sel.css("script#__UNIVERSAL_DATA_FOR_REHYDRATION__::text").get()
        if not raw:
            return links
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return links

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "id" and "author" in node and isinstance(node.get("author"), dict):
                        author = node["author"].get("uniqueId")
                        vid = node.get("id")
                        if author and vid:
                            links.add(f"https://www.tiktok.com/@{author}/video/{vid}")
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return links

    async def errback(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(repr(failure))
