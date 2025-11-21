import os
import google.generativeai as genai
from .models import Event, ScrapeResponse
import json
from typing import List
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

class GeminiExtractor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        from agent.processor import ContentProcessor
        self.processor = ContentProcessor()

    async def extract(self, content: str, screenshot_b64: str) -> ScrapeResponse:
        # Process content using ContentProcessor (JSON-LD + Markdown)
        processed_content = self.processor.process(content)
        
        prompt = """
        You are an intelligent event extractor. 
        I will provide you with the PROCESSED CONTENT (Markdown + JSON-LD) and a screenshot of a webpage for a SINGLE event.
        
        Your task is to extract the details of this specific event.
        
        Extract the following fields:
        - title: The name of the event.
        - date: The date of the event. Convert to YYYY-MM-DD if possible.
        - time: The time of the event (e.g., "6pm", "19:00").
        - location: The venue or address.
        - description: A brief description of the event (max 2-3 sentences).
        - link: The URL of the event page (if found in the content, otherwise null).
        
        IMPORTANT:
        - Prefer dates/times found in the "STRUCTURED EVENT DATA" section if available.
        - If the page contains multiple events, identify the main event or the first one.
        - If a field is missing, set it to null.
        
        Return the output strictly as a JSON object with a key "events" containing a list with the single event.
        Do not include any markdown formatting like ```json ... ``` in the response.
        """
        
        retries = 3
        base_delay = 2
        
        for attempt in range(retries):
            try:
                response = self.model.generate_content(
                    [
                        prompt,
                        {"mime_type": "image/png", "data": screenshot_b64},
                        processed_content 
                    ],
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=8192,
                        response_mime_type="application/json"
                    )
                )
                
                text_response = response.text
                
                try:
                    data = json.loads(text_response)
                except json.JSONDecodeError:
                    try:
                        last_brace = text_response.rfind("}")
                        if last_brace != -1:
                            repaired_json = text_response[:last_brace+1] + "]}"
                            data = json.loads(repaired_json)
                            return ScrapeResponse(events=[Event(**e) for e in data.get("events", [])], partial=True)
                        else:
                            raise
                    except Exception:
                         return ScrapeResponse(events=[], partial=False, error=f"JSON Decode Error")

                events = [Event(**e) for e in data.get("events", [])]
                
                # Post-process with authoritative JSON-LD dates if available
                json_ld_data = self.processor.get_json_ld_event_data()
                if json_ld_data and events:
                    event = events[0]
                    if 'startDate' in json_ld_data:
                        # Simple override for now, could be more sophisticated
                        # Just appending to description to verify it's being used for now, 
                        # or we could try to parse and replace. 
                        # Let's trust the LLM to have used it since we put it in the prompt.
                        pass

                return ScrapeResponse(events=events)
                
            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    import asyncio
                    sleep_time = base_delay * (2 ** attempt)
                    print(f"Hit 429, retrying in {sleep_time}s...")
                    await asyncio.sleep(sleep_time)
                    continue
                return ScrapeResponse(events=[], partial=False, error=str(e))
