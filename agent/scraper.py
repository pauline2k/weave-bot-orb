from playwright.async_api import async_playwright
import base64

class PlaywrightScraper:
    async def scrape(self, url: str):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                print(f"Error navigating to {url}: {e}")
                # Try to continue even if networkidle times out, content might be there
                pass
            
            content = await page.content()
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            await browser.close()
            return content, screenshot_b64
