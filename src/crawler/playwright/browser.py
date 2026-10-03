"""Playwright browser manager with anti-bot detection evasion."""

import asyncio
import json
import re
from typing import List, Optional, Set
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from src.config import get_config


class PlaywrightBrowser:
    """Quản lý trình duyệt Playwright với cấu hình vượt rào cản bot detection của TikTok."""

    def __init__(self, headless: Optional[bool] = None, timeout_ms: int = 30000):
        config = get_config().get("crawler", {}).get("browser", {})
        self.headless = headless if headless is not None else config.get("headless", True)
        self.timeout_ms = timeout_ms or config.get("timeout_ms", 30000)
        self.user_agent = config.get("user_agent", (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        self.viewport = config.get("viewport", {"width": 1280, "height": 800})
        self.args = config.get("args", [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ])
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=self.args,
            timeout=self.timeout_ms,
        )
        self._context = await self._browser.new_context(
            user_agent=self.user_agent,
            viewport=self.viewport,
            locale="en-US",
            ignore_https_errors=True,
        )

    async def new_page(self) -> Page:
        if not self._context:
            await self.start()
        page = await self._context.new_page()
        # Vô hiệu hóa navigator.webdriver
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        return page

    async def extract_video_urls(self, target_url: str, max_scrolls: int = 5) -> List[str]:
        """Trích xuất danh sách link video từ 1 trang TikTok (tag hoặc user)."""
        page = await self.new_page()
        video_links: Set[str] = set()

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                await page.wait_for_selector("a[href*='/video/']", state="attached", timeout=6000)
            except Exception:
                pass

            for _ in range(max_scrolls):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(1.5)

            content = await page.content()

            # Regex trích xuất URL video
            matches = re.findall(r'href="([^"]*?/video/\d+[^"]*?)"', content)
            for href in matches:
                if href.startswith("http"):
                    clean = href.split("?")[0]
                    video_links.add(clean)
                else:
                    clean = f"https://www.tiktok.com{href}".split("?")[0]
                    video_links.add(clean)

            # Khối JSON state nhúng
            json_matches = re.findall(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', content, re.DOTALL)
            if json_matches:
                try:
                    data = json.loads(json_matches[0])
                    video_links.update(self._extract_from_dict(data))
                except Exception:
                    pass

        finally:
            await page.close()

        return sorted(video_links)

    @staticmethod
    def _extract_from_dict(data: dict) -> Set[str]:
        links = set()

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "id" and "author" in node and isinstance(node.get("author"), dict):
                        author = node["author"].get("uniqueId")
                        vid = node.get("id")
                        if author and vid:
                            links.add(f"https://www.tiktok.com/@{author}/video/{vid}")
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return links

    async def close(self):
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
