"""Browser automation using Playwright."""
import asyncio
import base64
import logging
from typing import Optional, Dict, Any
import aiohttp
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
from agent.core.config import settings

logger = logging.getLogger(__name__)

# Minimum visible size (px) for an <img> to be considered "content" rather
# than an icon/avatar/logo when looking for a poster/flyer image to send
# to the LLM at full resolution.
MIN_CONTENT_IMAGE_DIMENSION = 200

# Selectors for common "sign up" / "log in to keep viewing" nag overlays
# that sit on top of the actual content on sites like Instagram. Best-effort
# only - if none match, we just proceed with whatever the page shows.
OVERLAY_CLOSE_SELECTORS = [
    '[role="dialog"] [aria-label="Close"]',
    '[aria-label="Close"]',
]


class BrowserManager:
    """Manages browser automation for web scraping."""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None

    async def __aenter__(self):
        """Start browser context."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=settings.headless
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close browser context."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _dismiss_overlays(self, page: Page) -> None:
        """Best-effort dismissal of sign-up/login nag modals.

        These overlays (common on Instagram, etc.) dim the underlying
        content and can obscure a poster/flyer image right when we're
        about to screenshot it. Closing them is safe even on sites that
        never trigger this - if nothing matches, we just move on.
        """
        for selector in OVERLAY_CLOSE_SELECTORS:
            try:
                close_btn = await page.query_selector(selector)
                if close_btn:
                    await close_btn.click(timeout=1000)
                    await asyncio.sleep(0.3)
                    return
            except Exception:
                continue

    async def _wait_for_images(self, page: Page, timeout: int = 5000) -> None:
        """Best-effort wait for visible large images to finish loading.

        Fixed sleeps alone can capture a page mid-lazy-load (e.g. a
        blurred low-res placeholder swapped for the full image a moment
        later). This waits for any large <img> to report itself loaded,
        but never blocks the pipeline if that never happens.
        """
        try:
            await page.wait_for_function(
                """(minDim) => {
                    const imgs = Array.from(document.querySelectorAll('img'))
                        .filter(img => img.width >= minDim && img.height >= minDim);
                    if (imgs.length === 0) return true;
                    return imgs.every(img => img.complete && img.naturalWidth > 0);
                }""",
                arg=MIN_CONTENT_IMAGE_DIMENSION,
                timeout=timeout,
            )
        except PlaywrightTimeout:
            pass
        except Exception:
            pass

    async def _find_content_image_url(self, page: Page) -> Optional[str]:
        """Find the largest "content" image on the page (e.g. a poster/flyer).

        Prefers images inside <article>/<main> and picks the largest by
        rendered area, ignoring small icons/avatars. This deliberately does
        NOT use the og:image meta tag - platforms like Instagram serve a
        square-cropped thumbnail there, which can crop out text (e.g. a
        date/time line) that's visible in the actual full-resolution image.
        """
        try:
            return await page.evaluate(
                """(minDim) => {
                    const scope = document.querySelector('article, main') || document.body;
                    const imgs = Array.from(scope.querySelectorAll('img'));
                    let best = null;
                    let bestArea = 0;
                    for (const img of imgs) {
                        const w = img.naturalWidth || img.width;
                        const h = img.naturalHeight || img.height;
                        if (w < minDim || h < minDim) continue;
                        const area = w * h;
                        if (area > bestArea) {
                            bestArea = area;
                            best = img.currentSrc || img.src;
                        }
                    }
                    return best;
                }""",
                MIN_CONTENT_IMAGE_DIMENSION,
            )
        except Exception:
            return None

    async def _download_image(self, url: str, referer: str) -> Optional[str]:
        """Download an image URL and return it as base64, or None on failure."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ),
                "Referer": referer,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Content image download got status {resp.status}")
                        return None
                    data = await resp.read()
                    if len(data) > 10 * 1024 * 1024:  # 10MB safety cap
                        logger.warning("Content image too large, skipping")
                        return None
                    return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to download content image: {e}")
            return None

    async def scrape_page(
        self,
        url: str,
        wait_time: int = 3000,
        include_screenshot: bool = True
    ) -> Dict[str, Any]:
        """
        Scrape a webpage and extract content.

        Args:
            url: The URL to scrape
            wait_time: Time to wait for page load in milliseconds
            include_screenshot: Whether to capture a screenshot

        Returns:
            Dictionary containing HTML, text, screenshot, and metadata
        """
        if not self.browser:
            raise RuntimeError("Browser not initialized. Use async context manager.")

        page = await self.browser.new_page()

        partial_load = False
        try:
            # Navigate to URL - use longer timeout, be fault-tolerant
            await page.goto(url, wait_until="networkidle", timeout=settings.browser_timeout)
        except PlaywrightTimeout:
            # Timeout is OK - continue with partial content (fault-tolerant approach)
            partial_load = True
        except Exception as e:
            # For other navigation errors, still try to extract what we can
            partial_load = True

        try:
            # Dismiss sign-up/login nag overlays before we look at the page,
            # so they don't dim/obscure content underneath.
            await self._dismiss_overlays(page)

            # Wait additional time for dynamic content
            await asyncio.sleep(wait_time / 1000)

            # Give large images a chance to finish loading past any
            # blurred/low-res placeholder stage.
            await self._wait_for_images(page)

            # Extract content - this works even on partial loads
            html_content = await page.content()
            text_content = await page.evaluate("() => document.body.innerText || ''")

            # Get page title
            title = await page.title()

            # Capture screenshot if requested
            screenshot_b64 = None
            if include_screenshot and settings.screenshot_enabled:
                try:
                    screenshot_bytes = await page.screenshot(full_page=True, type="png")
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                except Exception:
                    pass  # Screenshot failed, continue without it

            # Also try to find and download the largest "content" image
            # (e.g. an Instagram post's poster/flyer) at full resolution,
            # rather than relying solely on a shrunk full-page screenshot.
            content_image_b64 = None
            if include_screenshot and settings.screenshot_enabled:
                try:
                    image_url = await self._find_content_image_url(page)
                    if image_url:
                        content_image_b64 = await self._download_image(image_url, referer=url)
                except Exception:
                    pass  # Best-effort only

            # Consider it a success if we got any content
            has_content = bool(html_content and len(html_content) > 500)

            result = {
                "success": has_content,
                "url": url,
                "title": title,
                "html": html_content,
                "text": text_content,
                "screenshot": screenshot_b64,
                "content_image": content_image_b64,
                "error": "Partial page load (timeout)" if partial_load else None,
                "partial": partial_load
            }

        except PlaywrightTimeout as e:
            result = {
                "success": False,
                "url": url,
                "title": None,
                "html": None,
                "text": None,
                "screenshot": None,
                "content_image": None,
                "error": f"Timeout loading page: {str(e)}"
            }

        except Exception as e:
            result = {
                "success": False,
                "url": url,
                "title": None,
                "html": None,
                "text": None,
                "screenshot": None,
                "content_image": None,
                "error": f"Error scraping page: {str(e)}"
            }

        finally:
            await page.close()

        return result
