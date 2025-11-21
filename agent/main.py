from fastapi import FastAPI, HTTPException
from .models import ScrapeRequest, ScrapeResponse
from .scraper import PlaywrightScraper
from .extractor import GeminiExtractor
from dotenv import load_dotenv

from pathlib import Path

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = FastAPI()
scraper = PlaywrightScraper()
extractor = GeminiExtractor()

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_events(request: ScrapeRequest):
    try:
        content, screenshot_b64 = await scraper.scrape(request.url)
        response = await extractor.extract(content, screenshot_b64)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok"}
