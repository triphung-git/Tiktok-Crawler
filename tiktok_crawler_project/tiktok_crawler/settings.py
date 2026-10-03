BOT_NAME = "tiktok_crawler"

SPIDER_MODULES = ["tiktok_crawler.spiders"]
NEWSPIDER_MODULE = "tiktok_crawler.spiders"

# TikTok chặn phần lớn path trong robots.txt. Đặt False để spider có thể chạy,
# nhưng nên tự cân nhắc phạm vi crawl phù hợp với ToS của TikTok.
ROBOTSTXT_OBEY = False

# --- Tích hợp Playwright làm download handler ---
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "timeout": 30 * 1000,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30 * 1000
# Giới hạn số browser context mở song song để tránh ngốn RAM
PLAYWRIGHT_MAX_CONTEXTS = 4

PLAYWRIGHT_CONTEXTS = {
    "default": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
        "ignore_https_errors": True,
    }
}

# --- Rate limiting: TikTok rất nhạy với traffic bất thường ---
CONCURRENT_REQUESTS = 4
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 15

RETRY_TIMES = 3

ITEM_PIPELINES = {
    "tiktok_crawler.pipelines.JsonExportPipeline": 300,
}

FEED_EXPORT_ENCODING = "utf-8"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LOG_LEVEL = "INFO"
