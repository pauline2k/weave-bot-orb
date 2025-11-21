from pydantic import BaseModel
from typing import List, Optional

class Event(BaseModel):
    title: str
    date: str
    time: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None

class ScrapeRequest(BaseModel):
    url: str

class ScrapeResponse(BaseModel):
    events: List[Event]
    partial: bool = False
    error: Optional[str] = None
