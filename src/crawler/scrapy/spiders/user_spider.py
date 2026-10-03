"""User profile spider for TikTok crawling."""

from datetime import datetime, timezone
import scrapy

try:
    from src.crawler.scrapy.items import UserItem
except ModuleNotFoundError:
    from tiktok_crawler.items import UserItem


class UserSpider(scrapy.Spider):
    """
    Crawl danh sách video URL theo username (trang profile) trên TikTok.

    Cách chạy:
        scrapy crawl user -a usernames="vtv24news" -a max_scrolls=8 -a batch=WEEK3_0309
    """

    name = "user"
    allowed_domains = ["tiktok.com"]

    def __init__(self, usernames=None, max_scrolls=5, batch=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usernames = (
            [u.strip().lstrip("@") for u in usernames.split(",")] if usernames else []
        )
        self.max_scrolls = int(max_scrolls)
        self.batch = batch

    async def start(self):
        for req in self.start_requests():
            yield req

    def start_requests(self):
        if not self.usernames:
            self.logger.error("Chưa truyền username nào. Dùng: -a usernames=user1,user2")
            return

        for username in self.usernames:
            url = f"https://www.tiktok.com/@{username}"
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_context": "default",
                    "playwright_page_goto_kwargs": {
                        "wait_until": "domcontentloaded",
                    },
                    "username": username,
                },
                callback=self.parse_profile,
                errback=self.errback,
            )

    async def parse_profile(self, response):
        page = response.meta["playwright_page"]
        username = response.meta["username"]

        try:
            try:
                await page.wait_for_selector("a[href*='/video/']", state="attached", timeout=6000)
            except Exception:
                pass

            for _ in range(self.max_scrolls):
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1500)
            html = await page.content()
        finally:
            await page.close()

        sel = scrapy.Selector(text=html)
        video_links = set(sel.css("a[href*='/video/']::attr(href)").getall())

        for link in video_links:
            item = UserItem()
            item["username"] = username
            item["video_url"] = link if link.startswith("http") else f"https://www.tiktok.com{link}"
            item["author"] = username
            item["scraped_at"] = datetime.now(timezone.utc).isoformat()
            item["source_type"] = "user"
            yield item

    async def errback(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(repr(failure))
