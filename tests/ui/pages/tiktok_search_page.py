"""Page Object Model (POM) for TikTok Web Search & Feed UI Automation."""

from typing import List
from playwright.async_api import Page


class TikTokSearchPage:
    """Page Object representing TikTok Hashtag and Search Feed page."""

    # UI Locators
    SEARCH_INPUT = "input[type='search'], input[data-e2e='search-user-input']"
    VIDEO_CARD_ITEM = "div[data-e2e='challenge-item'], div[data-e2e='search_top-item']"
    VIDEO_LINKS = "a[href*='/video/']"
    CAPTCHA_MODAL = "div#captcha_container, div.verify-center"
    COOKIE_ACCEPT_BUTTON = "button[data-e2e='cookie-banner-accept'], button:has-text('Accept all')"

    def __init__(self, page: Page):
        self.page = page

    async def navigate_to_tag(self, tag: str, base_url: str = "https://www.tiktok.com"):
        """Navigates to the hashtag challenge feed page."""
        url = f"{base_url}/tag/{tag}"
        await self.page.goto(url, wait_until="domcontentloaded")

    async def accept_cookies_if_present(self):
        """Dismisses cookie consent banner if it appears on screen."""
        if await self.page.is_visible(self.COOKIE_ACCEPT_BUTTON):
            await self.page.click(self.COOKIE_ACCEPT_BUTTON)

    async def has_captcha_challenge(self) -> bool:
        """Checks if anti-bot Captcha challenge is currently blocking the screen."""
        return await self.page.is_visible(self.CAPTCHA_MODAL)

    async def scroll_page(self, distance: int = 1000):
        """Simulates humanized scrolling down the page to trigger infinite scroll loading."""
        await self.page.evaluate(f"window.scrollBy(0, {distance})")
        await self.page.wait_for_timeout(500)

    async def get_video_urls(self) -> List[str]:
        """Extracts and returns all discovered video URLs from the current DOM."""
        links = await self.page.query_selector_all(self.VIDEO_LINKS)
        urls = []
        for link in links:
            href = await link.get_attribute("href")
            if href and "/video/" in href:
                urls.append(href)
        return list(dict.fromkeys(urls))  # Deduplicate in-order
