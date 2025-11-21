import asyncio
import json
from agent.scraper import PlaywrightScraper
from agent.extractor import GeminiExtractor
import os

async def test_slow():
    scraper = PlaywrightScraper()
    extractor = GeminiExtractor()
    
    # Test URLs (one Instagram, one Eventbrite)
    urls = [
        "https://www.instagram.com/p/DQ-JfRrknSV/?ref=oaklandreviewofbooks.org",
        "https://www.eventbrite.com/e/kiss-tell-literary-salon-at-books-inc-alameda-tickets-1926171995289?aff=ebdsoporgprofile&ref=oaklandreviewofbooks.org"
    ]

    print(f"Testing scraping on {len(urls)} URLs with SLOW delays...")
    
    for i, url in enumerate(urls):
        print(f"\nScraping ({i+1}/{len(urls)}): {url}")
        try:
            content, screenshot_b64 = await scraper.scrape(url)
            response = await extractor.extract(content, screenshot_b64)
            
            if response.error:
                print(f"  FAILED: {response.error}")
            else:
                print(f"  SUCCESS: Found {len(response.events)} events")
                for event in response.events:
                    print(f"    - {event.title} ({event.date}) @ {event.location}")
        except Exception as e:
            print(f"  ERROR: {str(e)}")
            
        if i < len(urls) - 1:
            print("Waiting 30s before next request...")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(test_slow())
