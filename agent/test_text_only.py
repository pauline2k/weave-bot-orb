import asyncio
import json
from agent.scraper import PlaywrightScraper
from agent.extractor import GeminiExtractor
import google.generativeai as genai
import os

# Monkey patch extractor to skip image
original_extract = GeminiExtractor.extract

async def extract_text_only(self, content: str, screenshot_b64: str):
    cleaned_content = self.clean_html(content)
    cleaned_content = cleaned_content[:20000]
    
    prompt = """
    You are an intelligent event extractor. 
    I will provide you with the TEXT content of a webpage for a SINGLE event.
    
    Your task is to extract the details of this specific event.
    
    Extract the following fields:
    - title: The name of the event.
    - date: The date of the event. Convert to YYYY-MM-DD if possible.
    - time: The time of the event (e.g., "6pm", "19:00").
    - location: The venue or address.
    - description: A brief description of the event (max 2-3 sentences).
    - link: The URL of the event page (if found in the content, otherwise null).
    
    If a field is missing, set it to null.
    
    Return the output strictly as a JSON object with a key "events" containing a list with the single event.
    Do not include any markdown formatting like ```json ... ``` in the response.
    """
    
    retries = 5
    base_delay = 10
    
    for attempt in range(retries):
        try:
            # ONLY TEXT, NO IMAGE
            response = self.model.generate_content(
                [prompt, cleaned_content],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=8192,
                    response_mime_type="application/json"
                )
            )
            
            text_response = response.text
            try:
                data = json.loads(text_response)
                from agent.models import Event, ScrapeResponse
                events = [Event(**e) for e in data.get("events", [])]
                return ScrapeResponse(events=events)
            except Exception:
                 return ScrapeResponse(events=[], partial=False, error="JSON Decode Error")
            
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                import asyncio
                sleep_time = base_delay * (2 ** attempt)
                print(f"Hit 429, retrying in {sleep_time}s...")
                await asyncio.sleep(sleep_time)
                continue
            from agent.models import ScrapeResponse
            return ScrapeResponse(events=[], partial=False, error=str(e))

GeminiExtractor.extract = extract_text_only

async def test_text_only():
    scraper = PlaywrightScraper()
    extractor = GeminiExtractor()
    
    url = "https://www.eventbrite.com/e/kiss-tell-literary-salon-at-books-inc-alameda-tickets-1926171995289?aff=ebdsoporgprofile&ref=oaklandreviewofbooks.org"
    print(f"Testing TEXT-ONLY scraping on: {url}")
    
    try:
        content, screenshot_b64 = await scraper.scrape(url)
        response = await extractor.extract(content, screenshot_b64)
        
        if response.error:
            print(f"FAILED: {response.error}")
        else:
            print(f"SUCCESS: Found {len(response.events)} events")
            for event in response.events:
                print(f"  - {event.title} ({event.date})")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_text_only())
