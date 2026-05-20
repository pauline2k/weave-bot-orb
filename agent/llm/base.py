"""Abstract base class for LLM extractors."""
from abc import ABC, abstractmethod
from typing import Optional
from agent.core.schemas import Event


class LLMExtractor(ABC):
    """Abstract base class for LLM-based event extraction."""
    
    @abstractmethod
    async def extract_event(
        self, 
        url: str,
        content: str, 
        screenshot_b64: Optional[str] = None
    ) -> Event:
        """
        Extract event information from webpage content.
        
        Args:
            url: Source URL of the content
            content: Cleaned webpage content (text + HTML)
            screenshot_b64: Optional base64-encoded screenshot
            
        Returns:
            Extracted Event object
        """
        pass

    @abstractmethod
    async def extract_event_from_image(
        self,
        image_b64: str,
        source_description: Optional[str] = None
    ) -> Event:
        """
        Extract event information from an image.

        Args:
            image_b64: Base64-encoded image data
            source_description: Optional description of where the image came from

        Returns:
            Extracted Event object
        """
        pass
