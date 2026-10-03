"""Scrapy settings for TikTok crawler in the new pipeline structure."""

import os
from src.config import get_config

config = get_config()
crawler_cfg = config.get("crawler", {})
browser_cfg = crawler_cfg.get("browser", {})

BOT_NAME = crawler_cfg.get("bot_name", "tiktok_crawler")

SPIDER_MODULES = ["src.crawler.scrapy.spiders"]
NEWSPIDER_MODULE = "src.crawler.scrapy.spiders"

ROBOTSTXT_OBEY = crawler_cfg.get("robotstxt_obey", False)

# --- Playwright download handler ---
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = browser_cfg.get("browser_type", "chromium")
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": browser_cfg.get("headless", True),
    "timeout": browser_cfg.get("timeout_ms", 30000),
    "args": browser_cfg.get("args", [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]),
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = browser_cfg.get("timeout_ms", 30000)
PLAYWRIGHT_MAX_CONTEXTS = crawler_cfg.get("concurrent_requests", 4)

PLAYWRIGHT_CONTEXTS = {
    "default": {
        "user_agent": browser_cfg.get("user_agent", (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )),
        "viewport": browser_cfg.get("viewport", {"width": 1280, "height": 800}),
        "locale": browser_cfg.get("locale", "en-US"),
        "ignore_https_errors": True,
    }
}

# --- Rate limiting & concurrency ---
CONCURRENT_REQUESTS = crawler_cfg.get("concurrent_requests", 4)
DOWNLOAD_DELAY = crawler_cfg.get("download_delay", 2.0)
RANDOMIZE_DOWNLOAD_DELAY = crawler_cfg.get("randomize_download_delay", True)
AUTOTHROTTLE_ENABLED = crawler_cfg.get("autothrottle_enabled", True)
AUTOTHROTTLE_START_DELAY = crawler_cfg.get("autothrottle_start_delay", 2.0)
AUTOTHROTTLE_MAX_DELAY = crawler_cfg.get("autothrottle_max_delay", 15.0)

RETRY_TIMES = crawler_cfg.get("retry_times", 3)

ITEM_PIPELINES = {
    "src.crawler.scrapy.pipelines.JsonExportPipeline": 300,
}

FEED_EXPORT_ENCODING = "utf-8"
USER_AGENT = browser_cfg.get("user_agent", (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
