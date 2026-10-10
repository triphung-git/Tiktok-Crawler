"""UI Automation Testing with Playwright.

Implements Page Object Model (POM) tests for TikTok Web UI, anti-bot evasion
verification, element assertions, and screenshot on failure artifacts.
"""

import asyncio
from pathlib import Path
import pytest
from src.crawler.playwright.browser import PlaywrightBrowser
from tests.ui.pages.tiktok_search_page import TikTokSearchPage


def test_playwright_anti_bot_evasion():
    """TC-UI-01: Verify that Playwright successfully conceals navigator.webdriver."""
    async def _run():
        browser_manager = PlaywrightBrowser(headless=True)
        async with browser_manager:
            page = await browser_manager.new_page()
            # Verify navigator.webdriver is undefined
            webdriver_value = await page.evaluate("() => navigator.webdriver")
            assert webdriver_value in (None, False), (
                f"navigator.webdriver must not be True to bypass WAF bot detection, got: {webdriver_value}"
            )

    asyncio.run(_run())


def test_page_object_model_video_extraction():
    """TC-UI-04: Test POM extraction of video cards from DOM."""
    async def _run():
        mock_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div data-e2e="challenge-item">
                <a href="https://www.tiktok.com/@vtv24news/video/7234567890123456789">Video 1</a>
            </div>
            <div data-e2e="challenge-item">
                <a href="https://www.tiktok.com/@vtv24news/video/7234567890123456790">Video 2</a>
            </div>
            <div>
                <a href="https://www.tiktok.com/@vtv24news">User profile (not video)</a>
            </div>
        </body>
        </html>
        """
        browser_manager = PlaywrightBrowser(headless=True)
        async with browser_manager:
            page = await browser_manager.new_page()
            await page.set_content(mock_html)
            
            search_page = TikTokSearchPage(page)
            urls = await search_page.get_video_urls()
            
            assert len(urls) == 2
            assert "https://www.tiktok.com/@vtv24news/video/7234567890123456789" in urls
            assert "https://www.tiktok.com/@vtv24news/video/7234567890123456790" in urls

    asyncio.run(_run())


def test_cookie_consent_dismissal():
    """TC-UI-02: Test automated cookie banner dismissal."""
    async def _run():
        mock_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <button data-e2e="cookie-banner-accept">Accept all</button>
        </body>
        </html>
        """
        browser_manager = PlaywrightBrowser(headless=True)
        async with browser_manager:
            page = await browser_manager.new_page()
            await page.set_content(mock_html)
            
            search_page = TikTokSearchPage(page)
            assert await page.is_visible(TikTokSearchPage.COOKIE_ACCEPT_BUTTON) is True
            await search_page.accept_cookies_if_present()

    asyncio.run(_run())


def test_captcha_modal_detection():
    """TC-UI-02: Test automated detection of anti-bot captcha challenge modal."""
    async def _run():
        mock_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="captcha_container" style="display:block;">
                <p>Slide to complete the puzzle</p>
            </div>
        </body>
        </html>
        """
        browser_manager = PlaywrightBrowser(headless=True)
        async with browser_manager:
            page = await browser_manager.new_page()
            await page.set_content(mock_html)
            
            search_page = TikTokSearchPage(page)
            has_captcha = await search_page.has_captcha_challenge()
            assert has_captcha is True, "Must detect presence of Captcha modal in DOM"

    asyncio.run(_run())


def test_screenshot_on_failure_mechanism(tmp_path: Path):
    """TC-UI-05: Test automated capture of failure screenshot for defect investigation."""
    async def _run():
        screenshot_dir = tmp_path / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / "failed_ui_assertion.png"

        browser_manager = PlaywrightBrowser(headless=True)
        async with browser_manager:
            page = await browser_manager.new_page()
            await page.set_content("<html><body><h1>Simulated Error Page</h1></body></html>")
            
            # Capture screenshot as QA artifact
            await page.screenshot(path=str(screenshot_file))
            assert screenshot_file.is_file(), "Failure screenshot must be captured and persisted"
            assert screenshot_file.stat().st_size > 0

    asyncio.run(_run())
